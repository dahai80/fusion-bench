import { notFound } from "next/navigation";
import { getDb } from "@/db";
import { benchmarks } from "@/db/schema";
import { eq } from "drizzle-orm";
import Link from "next/link";

export const dynamic = "force-dynamic";

interface BatchingEntry {
    aggregate_tok_s?: number;
    per_request_tok_s?: number;
    mean_step_ms?: number;
}

function parseJson<T>(raw: string | null | undefined): T | null {
    if (!raw) return null;
    try {
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === "object" ? (parsed as T) : null;
    } catch {
        return null;
    }
}

function MetricCard({ label, value }: { label: string; value: string }) {
    return (
        <div className="bg-white rounded-2xl border border-neutral-200 p-5">
            <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">{label}</p>
            <p className="mt-2 text-2xl font-mono tabular-nums text-neutral-900">{value}</p>
        </div>
    );
}

function DetailRow({ label, value }: { label: string; value: string }) {
    return (
        <div className="flex justify-between gap-4 py-2 border-b border-neutral-100 last:border-0 sm:[&:nth-last-child(2)]:border-0">
            <dt className="text-neutral-500">{label}</dt>
            <dd className="font-mono text-neutral-900 text-right break-all">{value}</dd>
        </div>
    );
}

const TYPE_BADGES: Record<string, string> = {
    speed: "⚡ Speed",
    accuracy: "🎯 Accuracy",
    security: "🛡️ Security",
    quant: "📊 Quant",
    tune: "🔧 Tune",
};

export default async function BenchmarkDetailPage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = await params;
    const numericId = parseInt(id, 10);
    if (Number.isNaN(numericId)) notFound();

    const db = getDb();
    const row = db.select().from(benchmarks).where(eq(benchmarks.id, numericId)).get();
    if (!row) notFound();

    const bType = (row as Record<string, unknown>).benchmarkType as string || "speed";
    const taskName = (row as Record<string, unknown>).taskName as string || "";
    const metricName = (row as Record<string, unknown>).metricName as string || "decode_speed";
    const metricValue = (row as Record<string, unknown>).metricValue as number ?? 0;
    const detail = parseJson<Record<string, unknown>>((row as Record<string, unknown>).detail as string | null | undefined);
    const batching = parseJson<Record<string, BatchingEntry>>(row.batchingResults);

    const created = new Date(row.createdAt);

    const systemDetails = [
        { label: "Chip", value: row.chipVariant ? `${row.chipName} (${row.chipVariant})` : row.chipName },
        { label: "Memory", value: `${row.memoryGb} GB` },
        { label: "GPU Cores", value: String(row.gpuCores) },
        { label: "OS", value: row.osVersion || "—" },
        { label: "MLX Version", value: row.omlxVersion || "—" },
        { label: "Context Length", value: row.contextLength.toLocaleString() },
        { label: "Submission Group", value: row.submissionGroup || "—" },
        { label: "Owner Hash", value: row.ownerHash || "—" },
        { label: "Submitted", value: created.toLocaleString() },
    ];

    const batchingRows = batching
        ? Object.entries(batching).sort(([a], [b]) => Number(a) - Number(b))
        : [];

    const renderMetrics = () => {
        if (bType === "speed") {
            return (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
                    <MetricCard label="tg TPS" value={row.tgTps.toFixed(1)} />
                    <MetricCard label="pp TPS" value={row.ppTps.toFixed(1)} />
                    <MetricCard label="TTFT (ms)" value={row.ttftMs != null ? row.ttftMs.toFixed(0) : "—"} />
                    <MetricCard label="Peak Mem (GB)" value={row.peakMemoryGb != null ? row.peakMemoryGb.toFixed(1) : "—"} />
                </div>
            );
        }

        if (bType === "accuracy" && detail) {
            const acc = (detail.accuracy as number) ?? metricValue;
            const passRate = detail.pass_rate as number | undefined;
            const fewshot = detail.num_fewshot as number | undefined;
            return (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
                    <MetricCard label="Accuracy" value={`${(acc * 100).toFixed(2)}%`} />
                    {passRate != null && <MetricCard label="Pass Rate" value={`${(passRate * 100).toFixed(1)}%`} />}
                    {fewshot != null && <MetricCard label="Num Fewshot" value={String(fewshot)} />}
                    <MetricCard label={metricName} value={metricValue.toFixed(4)} />
                </div>
            );
        }

        if (bType === "security" && detail) {
            const safetyRate = (detail.safety_rate as number) ?? metricValue;
            const safeCount = detail.safe_count as number | undefined;
            const totalProbes = detail.total_probes as number | undefined;
            const probeSet = detail.probe_set as string | undefined;
            return (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
                    <MetricCard label="Safety Rate" value={`${(safetyRate * 100).toFixed(1)}%`} />
                    {safeCount != null && <MetricCard label="Safe Count" value={String(safeCount)} />}
                    {totalProbes != null && <MetricCard label="Total Probes" value={String(totalProbes)} />}
                    {probeSet && <MetricCard label="Probe Set" value={probeSet} />}
                </div>
            );
        }

        if (bType === "quant" && detail) {
            const levels = detail.levels as Array<Record<string, unknown>> | undefined;
            return (
                <>
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
                        <MetricCard label="Metric" value={metricName} />
                        <MetricCard label="Best Value" value={metricValue.toFixed(2)} />
                    </div>
                    {levels && levels.length > 0 && (
                        <div className="bg-white rounded-2xl border border-neutral-200 overflow-hidden mb-10">
                            <div className="px-6 py-4 border-b border-neutral-200">
                                <h2 className="text-lg font-semibold text-neutral-900">Quantization Levels</h2>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="bg-neutral-50 border-b border-neutral-200">
                                            <th className="text-left px-4 py-3 font-medium text-neutral-500">Level</th>
                                            <th className="text-right px-4 py-3 font-medium text-neutral-500">Speed (tok/s)</th>
                                            <th className="text-right px-4 py-3 font-medium text-neutral-500">Accuracy</th>
                                            <th className="text-right px-4 py-3 font-medium text-neutral-500">Memory (GB)</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {levels.map((lv, i) => (
                                            <tr key={i} className="border-b border-neutral-100 last:border-0">
                                                <td className="px-4 py-3 font-medium text-neutral-900">{String(lv.quantization || lv.level || i)}</td>
                                                <td className="px-4 py-3 text-right font-mono tabular-nums text-neutral-900">
                                                    {lv.speed != null ? Number(lv.speed).toFixed(2) : "—"}
                                                </td>
                                                <td className="px-4 py-3 text-right font-mono tabular-nums text-neutral-600">
                                                    {lv.accuracy != null ? `${(Number(lv.accuracy) * 100).toFixed(1)}%` : "—"}
                                                </td>
                                                <td className="px-4 py-3 text-right font-mono tabular-nums text-neutral-600">
                                                    {lv.memory_gb != null ? Number(lv.memory_gb).toFixed(1) : "—"}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </>
            );
        }

        if (bType === "tune" && detail) {
            const bestConfig = detail.best_config as Record<string, unknown> | undefined;
            const top3 = detail.top3 as Array<Record<string, unknown>> | undefined;
            const memSaving = detail.memory_saving as number | undefined;
            return (
                <>
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
                        <MetricCard label="Best Score" value={metricValue.toFixed(2)} />
                        <MetricCard label="Metric" value={metricName} />
                        {memSaving != null && <MetricCard label="Memory Saving" value={`${(memSaving * 100).toFixed(1)}%`} />}
                    </div>
                    {bestConfig && (
                        <div className="bg-white rounded-2xl border border-neutral-200 p-6 mb-10">
                            <h2 className="text-lg font-semibold text-neutral-900 mb-4">Best Configuration</h2>
                            <dl className="grid sm:grid-cols-2 gap-x-8 gap-y-1 text-sm">
                                {Object.entries(bestConfig).map(([k, v]) => (
                                    <DetailRow key={k} label={k} value={String(v)} />
                                ))}
                            </dl>
                        </div>
                    )}
                    {top3 && top3.length > 0 && (
                        <div className="bg-white rounded-2xl border border-neutral-200 overflow-hidden mb-10">
                            <div className="px-6 py-4 border-b border-neutral-200">
                                <h2 className="text-lg font-semibold text-neutral-900">Top 3 Configs</h2>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="bg-neutral-50 border-b border-neutral-200">
                                            <th className="text-left px-4 py-3 font-medium text-neutral-500">Rank</th>
                                            <th className="text-left px-4 py-3 font-medium text-neutral-500">Config</th>
                                            <th className="text-right px-4 py-3 font-medium text-neutral-500">Score</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {top3.map((cfg, i) => (
                                            <tr key={i} className="border-b border-neutral-100 last:border-0">
                                                <td className="px-4 py-3 font-medium text-neutral-900">#{i + 1}</td>
                                                <td className="px-4 py-3 text-neutral-600 text-xs font-mono">
                                                    {Object.entries(cfg).filter(([k]) => k !== "score").map(([k, v]) => `${k}=${v}`).join(", ")}
                                                </td>
                                                <td className="px-4 py-3 text-right font-mono tabular-nums text-neutral-900">
                                                    {cfg.score != null ? Number(cfg.score).toFixed(2) : "—"}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </>
            );
        }

        return (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
                <MetricCard label="Metric" value={metricName} />
                <MetricCard label="Value" value={metricValue.toFixed(4)} />
                {bType === "speed" && <MetricCard label="tg TPS" value={row.tgTps.toFixed(1)} />}
                {bType === "speed" && <MetricCard label="pp TPS" value={row.ppTps.toFixed(1)} />}
            </div>
        );
    };

    return (
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
            <Link href="/benchmarks" className="text-sm text-neutral-500 hover:text-neutral-900 transition-colors">
                ← Back to Benchmarks
            </Link>

            <div className="mt-4 mb-8">
                <div className="flex flex-wrap items-center gap-3">
                    <h1 className="text-3xl font-bold text-neutral-900">{row.modelName}</h1>
                    <span className="inline-flex px-2.5 py-1 rounded-md bg-neutral-100 text-neutral-600 text-sm font-medium">
                        {row.quantization}
                    </span>
                    <span className="inline-flex px-2.5 py-1 rounded-md bg-neutral-900 text-white text-sm font-medium">
                        {TYPE_BADGES[bType] || bType}
                    </span>
                    {taskName && (
                        <span className="inline-flex px-2.5 py-1 rounded-md bg-neutral-100 text-neutral-500 text-xs font-medium">
                            {taskName}
                        </span>
                    )}
                </div>
                <p className="mt-2 text-neutral-500">
                    {row.chipName} · {row.memoryGb} GB · {row.contextLength.toLocaleString()} context · {created.toLocaleDateString()}
                </p>
            </div>

            {renderMetrics()}

            <div className="bg-white rounded-2xl border border-neutral-200 p-6 mb-10">
                <h2 className="text-lg font-semibold text-neutral-900 mb-4">System Details</h2>
                <dl className="grid sm:grid-cols-2 gap-x-8 gap-y-1 text-sm">
                    {systemDetails.map((d) => (
                        <DetailRow key={d.label} label={d.label} value={d.value} />
                    ))}
                </dl>
            </div>

            {bType === "speed" && batchingRows.length > 0 && (
                <div className="bg-white rounded-2xl border border-neutral-200 overflow-hidden">
                    <div className="px-6 py-4 border-b border-neutral-200">
                        <h2 className="text-lg font-semibold text-neutral-900">Batching Results</h2>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="bg-neutral-50 border-b border-neutral-200">
                                    <th className="text-left px-4 py-3 font-medium text-neutral-500">Batch Size</th>
                                    <th className="text-right px-4 py-3 font-medium text-neutral-500">Aggregate tok/s</th>
                                    <th className="text-right px-4 py-3 font-medium text-neutral-500">Per-request tok/s</th>
                                    <th className="text-right px-4 py-3 font-medium text-neutral-500">Step (ms)</th>
                                </tr>
                            </thead>
                            <tbody>
                                {batchingRows.map(([bs, r]) => (
                                    <tr key={bs} className="border-b border-neutral-100 last:border-0">
                                        <td className="px-4 py-3 font-medium text-neutral-900">{bs}</td>
                                        <td className="px-4 py-3 text-right font-mono tabular-nums text-neutral-900">
                                            {r.aggregate_tok_s != null ? r.aggregate_tok_s.toFixed(2) : "—"}
                                        </td>
                                        <td className="px-4 py-3 text-right font-mono tabular-nums text-neutral-600">
                                            {r.per_request_tok_s != null ? r.per_request_tok_s.toFixed(2) : "—"}
                                        </td>
                                        <td className="px-4 py-3 text-right font-mono tabular-nums text-neutral-600">
                                            {r.mean_step_ms != null ? r.mean_step_ms.toFixed(1) : "—"}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {bType !== "speed" && detail && (
                <div className="bg-white rounded-2xl border border-neutral-200 overflow-hidden mt-10">
                    <details>
                        <summary className="px-6 py-4 cursor-pointer text-sm font-medium text-neutral-500 hover:text-neutral-900">
                            Raw Detail JSON
                        </summary>
                        <pre className="px-6 pb-4 text-xs font-mono text-neutral-700 overflow-x-auto">
                            {JSON.stringify(detail, null, 2)}
                        </pre>
                    </details>
                </div>
            )}
        </div>
    );
}
