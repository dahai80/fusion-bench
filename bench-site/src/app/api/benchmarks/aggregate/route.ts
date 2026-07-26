import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/db";
import { benchmarks } from "@/db/schema";
import { eq, and, like, sql } from "drizzle-orm";

const VALID_GROUP_BY = ["model", "chip", "quant", "type", "task"] as const;
const VALID_METRICS = ["tg_tps", "pp_tps", "ttft_ms", "metric_value"] as const;

const GROUP_COL_MAP: Record<string, string> = {
    model: "model_name",
    chip: "chip_name",
    quant: "quantization",
    type: "benchmark_type",
    task: "task_name",
};

const METRIC_COL_MAP: Record<string, string> = {
    tg_tps: "tg_tps",
    pp_tps: "pp_tps",
    ttft_ms: "ttft_ms",
    metric_value: "metric_value",
};

function escapeLike(input: string): string {
    return input.replace(/[%_\\]/g, "\\$&");
}

export async function GET(request: NextRequest) {
    try {
        const { searchParams } = new URL(request.url);
        const db = getDb();

        const rawGroupBy = searchParams.get("group_by") || "model";
        const rawMetric = searchParams.get("metric") || "tg_tps";
        const chip = searchParams.get("chip");
        const quant = searchParams.get("quant");
        const benchmarkType = searchParams.get("benchmark_type");
        const taskName = searchParams.get("task_name");

        // Validate group_by and metric against whitelists
        const groupBy = VALID_GROUP_BY.includes(rawGroupBy as typeof VALID_GROUP_BY[number])
            ? rawGroupBy : "model";
        const metric = VALID_METRICS.includes(rawMetric as typeof VALID_METRICS[number])
            ? rawMetric : "tg_tps";

        // Build WHERE conditions using drizzle ORM (parameterized)
        const conditions = [];
        if (chip) conditions.push(like(benchmarks.chipName, `%${escapeLike(chip)}%`));
        if (quant) conditions.push(eq(benchmarks.quantization, quant));
        if (benchmarkType) conditions.push(eq(benchmarks.benchmarkType, benchmarkType));
        if (taskName) conditions.push(eq(benchmarks.taskName, taskName));

        const groupCol = GROUP_COL_MAP[groupBy];
        const metricCol = METRIC_COL_MAP[metric];

        // Use parameterized query via drizzle — groupCol and metricCol are
        // whitelisted strings (not user input), so sql.identifier is safe here.
        const whereClause = conditions.length > 0 ? and(...conditions) : undefined;

        const rows = db
            .select({
                key: sql`${sql.identifier(groupCol)}`,
                avg: sql<number>`round(avg(${sql.identifier(metricCol)}), 2)`,
                max: sql<number>`round(max(${sql.identifier(metricCol)}), 2)`,
                min: sql<number>`round(min(${sql.identifier(metricCol)}), 2)`,
                count: sql<number>`count(*)`,
            })
            .from(benchmarks)
            .where(whereClause)
            .groupBy(sql`${sql.identifier(groupCol)}`)
            .orderBy(sql`avg(${sql.identifier(metricCol)}) DESC`)
            .all();

        return NextResponse.json({ groups: rows });
    } catch (e: unknown) {
        console.error("Aggregate API error:", e);
        return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
    }
}
