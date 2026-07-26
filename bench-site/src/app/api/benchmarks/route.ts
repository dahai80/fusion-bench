import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/db";
import { benchmarks } from "@/db/schema";
import { eq, and, desc, asc, sql, like } from "drizzle-orm";

// Escape LIKE metacharacters (% and _) in user input
function escapeLike(input: string): string {
    return input.replace(/[%_\\]/g, "\\$&");
}

function safeJsonParse(raw: string | null | undefined): unknown {
    if (!raw) return null;
    try {
        return JSON.parse(raw);
    } catch {
        return null;
    }
}

// Validate numeric fields from POST body
function validatePostBody(body: Record<string, unknown>): string | null {
    if (typeof body.chip_name !== "string" || body.chip_name.length > 128) return "Invalid chip_name";
    if (typeof body.memory_gb !== "number" || body.memory_gb < 0 || body.memory_gb > 1024) return "Invalid memory_gb";
    if (typeof body.gpu_cores !== "number" || body.gpu_cores < 0 || body.gpu_cores > 256) return "Invalid gpu_cores";
    if (typeof body.model_name !== "string" || body.model_name.length > 256) return "Invalid model_name";
    if (typeof body.quantization !== "string" || body.quantization.length > 64) return "Invalid quantization";
    if (typeof body.context_length !== "number" || body.context_length < 1 || body.context_length > 1000000) return "Invalid context_length";
    if (typeof body.submission_group !== "string" || body.submission_group.length > 128) return "Invalid submission_group";
    if (body.pp_tps != null && (typeof body.pp_tps !== "number" || body.pp_tps < 0)) return "Invalid pp_tps";
    if (body.tg_tps != null && (typeof body.tg_tps !== "number" || body.tg_tps < 0)) return "Invalid tg_tps";
    if (body.ttft_ms != null && (typeof body.ttft_ms !== "number" || body.ttft_ms < 0)) return "Invalid ttft_ms";
    if (body.peak_memory_gb != null && (typeof body.peak_memory_gb !== "number" || body.peak_memory_gb < 0)) return "Invalid peak_memory_gb";
    if (body.metric_value != null && (typeof body.metric_value !== "number" || !isFinite(body.metric_value))) return "Invalid metric_value";
    if (body.benchmark_type != null && (typeof body.benchmark_type !== "string" || !["speed", "accuracy", "security", "quant", "tune"].includes(body.benchmark_type))) return "Invalid benchmark_type";
    if (body.metric_name != null && (typeof body.metric_name !== "string" || body.metric_name.length > 128)) return "Invalid metric_name";
    if (body.task_name != null && (typeof body.task_name !== "string" || body.task_name.length > 128)) return "Invalid task_name";
    return null;
}

export async function POST(request: NextRequest) {
    try {
        const body = await request.json();

        const required = ["chip_name", "memory_gb", "gpu_cores", "model_name", "quantization", "context_length", "submission_group"];
        for (const field of required) {
            if (body[field] === undefined || body[field] === null) {
                return NextResponse.json({ detail: `Missing required field: ${field}` }, { status: 400 });
            }
        }

        const validationError = validatePostBody(body);
        if (validationError) {
            return NextResponse.json({ detail: validationError }, { status: 400 });
        }

        const db = getDb();

        // Dedup: same owner_hash + chip + model + quant + context_length + benchmark_type + task_name
        if (body.owner_hash) {
            const dedupConditions = [
                eq(benchmarks.ownerHash, body.owner_hash),
                eq(benchmarks.chipName, body.chip_name),
                eq(benchmarks.modelName, body.model_name),
                eq(benchmarks.quantization, body.quantization),
                eq(benchmarks.contextLength, body.context_length),
                eq(benchmarks.benchmarkType, body.benchmark_type || "speed"),
            ];
            const taskName = body.task_name || "";
            if (taskName) {
                dedupConditions.push(eq(benchmarks.taskName, taskName));
            }

            const existing = db.select({ id: benchmarks.id }).from(benchmarks).where(
                and(...dedupConditions),
            ).get();

            if (existing) {
                const url = `${process.env.NEXT_PUBLIC_SITE_URL || "http://bench.dpdns.org"}/benchmarks/${existing.id}`;
                return NextResponse.json({ existing_id: existing.id, existing_url: url }, { status: 409 });
            }
        }

        const result = db.insert(benchmarks).values({
            chipName: body.chip_name,
            chipVariant: body.chip_variant || "",
            memoryGb: body.memory_gb,
            gpuCores: body.gpu_cores,
            osVersion: body.os_version || "",
            omlxVersion: body.omlx_version || "",
            modelName: body.model_name,
            quantization: body.quantization,
            contextLength: body.context_length,
            ppTps: body.pp_tps ?? 0,
            tgTps: body.tg_tps ?? 0,
            ttftMs: body.ttft_ms ?? null,
            peakMemoryGb: body.peak_memory_gb ?? null,
            batchingResults: body.batching_results ? JSON.stringify(body.batching_results) : "",
            ownerHash: body.owner_hash || "",
            submissionGroup: body.submission_group,
            benchmarkType: body.benchmark_type || "speed",
            taskName: body.task_name || "",
            metricName: body.metric_name || "decode_speed",
            metricValue: body.metric_value ?? 0,
            detail: body.detail || "{}",
        }).returning({ id: benchmarks.id }).get();

        const url = `${process.env.NEXT_PUBLIC_SITE_URL || "http://bench.dpdns.org"}/benchmarks/${result.id}`;
        return NextResponse.json({ id: result.id, url }, { status: 201 });
    } catch (e: unknown) {
        console.error("Benchmarks POST error:", e);
        return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
    }
}

export async function GET(request: NextRequest) {
    try {
        const { searchParams } = new URL(request.url);
        const db = getDb();

        const chip = searchParams.get("chip");
        const model = searchParams.get("model");
        const quant = searchParams.get("quant");
        const ctxLen = searchParams.get("context_length");
        const ownerHash = searchParams.get("owner_hash");
        const benchmarkType = searchParams.get("benchmark_type");
        const taskName = searchParams.get("task_name");
        const sort = searchParams.get("sort") || "created_at";
        const order = searchParams.get("order") || "desc";
        const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10) || 1);
        const rawLimit = parseInt(searchParams.get("limit") || "50", 10) || 50;
        const limit = rawLimit === 0 ? 0 : Math.min(100, Math.max(1, rawLimit));

        const conditions = [];
        if (chip) conditions.push(like(benchmarks.chipName, `%${escapeLike(chip)}%`));
        if (model) conditions.push(like(benchmarks.modelName, `%${escapeLike(model)}%`));
        if (quant) conditions.push(eq(benchmarks.quantization, quant));
        if (ctxLen) {
            const parsedCtxLen = parseInt(ctxLen, 10);
            if (!Number.isNaN(parsedCtxLen)) conditions.push(eq(benchmarks.contextLength, parsedCtxLen));
        }
        if (ownerHash) conditions.push(eq(benchmarks.ownerHash, ownerHash));
        if (benchmarkType) conditions.push(eq(benchmarks.benchmarkType, benchmarkType));
        if (taskName) conditions.push(eq(benchmarks.taskName, taskName));

        const where = conditions.length > 0 ? and(...conditions) : undefined;

        const sortCol = sort === "tg_tps" ? benchmarks.tgTps
            : sort === "pp_tps" ? benchmarks.ppTps
            : sort === "ttft_ms" ? benchmarks.ttftMs
            : sort === "metric_value" ? benchmarks.metricValue
            : sort === "model_name" ? benchmarks.modelName
            : sort === "chip_name" ? benchmarks.chipName
            : sort === "context_length" ? benchmarks.contextLength
            : benchmarks.createdAt;

        const orderBy = order === "asc" ? asc(sortCol) : desc(sortCol);

        const query = limit > 0
            ? db.select().from(benchmarks).where(where).orderBy(orderBy).limit(limit).offset((page - 1) * limit)
            : db.select().from(benchmarks).where(where).orderBy(orderBy);
        const [data, countResult] = await Promise.all([
            query,
            db.select({ count: sql<number>`count(*)` }).from(benchmarks).where(where),
        ]);

        const total = countResult[0]?.count ?? 0;

        return NextResponse.json({
            data: data.map((row) => ({
                ...row,
                batching_results: safeJsonParse(row.batchingResults),
                detail: safeJsonParse(row.detail),
            })),
            total,
            page,
            limit,
        });
    } catch (e: unknown) {
        console.error("Benchmarks GET error:", e);
        return NextResponse.json({ detail: "Internal server error" }, { status: 500 });
    }
}
