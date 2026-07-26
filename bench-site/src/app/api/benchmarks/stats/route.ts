import { NextResponse } from "next/server";
import { getDb } from "@/db";
import { benchmarks } from "@/db/schema";
import { sql, desc } from "drizzle-orm";

function safeJsonParse(raw: string | null | undefined): unknown {
    if (!raw) return null;
    try {
        return JSON.parse(raw);
    } catch {
        return null;
    }
}

export async function GET() {
    try {
        const db = getDb();

        const [totalResult, chipResult, modelResult, typeResult, latestResult] = await Promise.all([
            db.select({ count: sql<number>`count(*)` }).from(benchmarks),
            db.select({ count: sql<number>`count(distinct ${benchmarks.chipName})` }).from(benchmarks),
            db.select({ count: sql<number>`count(distinct ${benchmarks.modelName})` }).from(benchmarks),
            db.select({
                type: benchmarks.benchmarkType,
                count: sql<number>`count(*)`,
            }).from(benchmarks).groupBy(benchmarks.benchmarkType),
            db.select().from(benchmarks).orderBy(desc(benchmarks.createdAt)).limit(10),
        ]);

        return NextResponse.json({
            total_submissions: totalResult[0]?.count ?? 0,
            total_chips: chipResult[0]?.count ?? 0,
            total_models: modelResult[0]?.count ?? 0,
            by_type: typeResult.reduce((acc, r) => {
                acc[r.type] = r.count;
                return acc;
            }, {} as Record<string, number>),
            latest: latestResult.map((row) => ({
                ...row,
                batching_results: safeJsonParse(row.batchingResults),
                detail: safeJsonParse(row.detail),
            })),
        });
    } catch (e: unknown) {
        
        console.error("API error:", e); return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
    }
}
