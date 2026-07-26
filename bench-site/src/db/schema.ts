import { sql } from "drizzle-orm";
import { sqliteTable, text, integer, real, index } from "drizzle-orm/sqlite-core";

export const benchmarks = sqliteTable(
    "benchmarks",
    {
        id: integer("id").primaryKey({ autoIncrement: true }),
        createdAt: text("created_at").default(sql`(datetime('now'))`).notNull(),

        chipName: text("chip_name").notNull(),
        chipVariant: text("chip_variant").default(""),
        memoryGb: integer("memory_gb").notNull(),
        gpuCores: integer("gpu_cores").notNull(),
        osVersion: text("os_version").default(""),

        omlxVersion: text("omlx_version").default(""),

        modelName: text("model_name").notNull(),
        quantization: text("quantization").notNull(),
        contextLength: integer("context_length").notNull(),

        ppTps: real("pp_tps").notNull().default(0),
        tgTps: real("tg_tps").notNull().default(0),
        ttftMs: real("ttft_ms"),
        peakMemoryGb: real("peak_memory_gb"),

        batchingResults: text("batching_results").default(""),

        ownerHash: text("owner_hash").default(""),
        submissionGroup: text("submission_group").notNull(),

        benchmarkType: text("benchmark_type").notNull().default("speed"),
        taskName: text("task_name").default(""),
        metricName: text("metric_name").default("decode_speed"),
        metricValue: real("metric_value").default(0),
        detail: text("detail").default("{}"),
    },
    (table) => [
        index("idx_bench_model").on(table.modelName, table.quantization),
        index("idx_bench_chip").on(table.chipName, table.memoryGb),
        index("idx_bench_owner").on(table.ownerHash),
        index("idx_bench_created").on(table.createdAt),
        index("idx_bench_type").on(table.benchmarkType),
        index("idx_bench_task").on(table.taskName),
    ],
);
