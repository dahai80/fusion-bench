// Multi-model interactive comparison page for bench-site.
// Importers/callers: Next.js App Router, linked from navbar.
// Affected API: consumes /api/benchmarks endpoint; no new API.
// Data schema: uses existing Benchmark interface from benchmarks/page.tsx.
// User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (Enhancement D multi-model compare).

"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";

interface Benchmark {
    id: number;
    createdAt: string;
    chipName: string;
    chipVariant: string;
    memoryGb: number;
    gpuCores: number;
    osVersion: string;
    omlxVersion: string;
    modelName: string;
    quantization: string;
    contextLength: number;
    ppTps: number;
    tgTps: number;
    ttftMs: number | null;
    peakMemoryGb: number | null;
    ownerHash: string;
    benchmarkType: string;
    taskName: string;
    metricName: string;
    metricValue: number;
    detail: Record<string, unknown> | null;
}

const METRICS = ["tg_tps", "pp_tps", "ttft_ms", "metric_value", "peak_memory_gb"] as const;
const METRIC_LABELS: Record<string, string> = {
    tg_tps: "Decode Speed (tok/s)",
    pp_tps: "Prefill Speed (tok/s)",
    ttft_ms: "TTFT (ms)",
    metric_value: "Accuracy",
    peak_memory_gb: "Peak Memory (GB)",
};

export default function ComparePage() {
    const [benchmarks, setBenchmarks] = useState<Benchmark[]>([]);
    const [selectedModels, setSelectedModels] = useState<string[]>([]);
    const [selectedMetric, setSelectedMetric] = useState<string>("tg_tps");
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch("/api/benchmarks?limit=500")
            .then((r) => r.json())
            .then((data) => {
                setBenchmarks(data.benchmarks || data || []);
                setLoading(false);
            })
            .catch(() => setLoading(false));
    }, []);

    const uniqueModels = useCallback(() => {
        const models = new Set<string>();
        benchmarks.forEach((b) => models.add(b.modelName));
        return Array.from(models).sort();
    }, [benchmarks]);

    const toggleModel = (model: string) => {
        setSelectedModels((prev) =>
            prev.includes(model) ? prev.filter((m) => m !== model) : [...prev, model]
        );
    };

    const filtered = benchmarks.filter((b) => selectedModels.includes(b.modelName));

    const avgByModel = useCallback(() => {
        const groups: Record<string, number[]> = {};
        filtered.forEach((b) => {
            const val = (b as Record<string, unknown>)[selectedMetric] as number;
            if (val != null && !isNaN(val)) {
                if (!groups[b.modelName]) groups[b.modelName] = [];
                groups[b.modelName].push(val);
            }
        });
        return Object.entries(groups).map(([model, vals]) => ({
            model,
            avg: vals.reduce((a, b) => a + b, 0) / vals.length,
            min: Math.min(...vals),
            max: Math.max(...vals),
            count: vals.length,
        }));
    }, [filtered, selectedMetric]);

    const chartData = avgByModel();
    const maxVal = Math.max(...chartData.map((d) => d.max), 1);

    return (
        <div className="min-h-screen bg-gray-950 text-gray-100">
            <div className="max-w-7xl mx-auto px-4 py-8">
                <div className="flex items-center justify-between mb-8">
                    <h1 className="text-3xl font-bold">Model Comparison</h1>
                    <Link href="/benchmarks" className="text-blue-400 hover:text-blue-300">
                        ← Back to Benchmarks
                    </Link>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                    <div className="lg:col-span-1 space-y-4">
                        <div className="bg-gray-900 rounded-lg p-4">
                            <h3 className="text-sm font-semibold mb-3 text-gray-400 uppercase">
                                Select Models
                            </h3>
                            <div className="space-y-2 max-h-96 overflow-y-auto">
                                {uniqueModels().map((model) => (
                                    <label key={model} className="flex items-center gap-2 cursor-pointer">
                                        <input
                                            type="checkbox"
                                            checked={selectedModels.includes(model)}
                                            onChange={() => toggleModel(model)}
                                            className="rounded border-gray-600 bg-gray-800 text-blue-500"
                                        />
                                        <span className="text-sm truncate">{model}</span>
                                    </label>
                                ))}
                            </div>
                        </div>

                        <div className="bg-gray-900 rounded-lg p-4">
                            <h3 className="text-sm font-semibold mb-3 text-gray-400 uppercase">
                                Metric
                            </h3>
                            <select
                                value={selectedMetric}
                                onChange={(e) => setSelectedMetric(e.target.value)}
                                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
                            >
                                {METRICS.map((m) => (
                                    <option key={m} value={m}>
                                        {METRIC_LABELS[m]}
                                    </option>
                                ))}
                            </select>
                        </div>

                        <div className="bg-gray-900 rounded-lg p-4">
                            <p className="text-sm text-gray-400">
                                {selectedModels.length} models · {filtered.length} data points
                            </p>
                        </div>
                    </div>

                    <div className="lg:col-span-3 space-y-6">
                        {chartData.length > 0 && (
                            <div className="bg-gray-900 rounded-lg p-6">
                                <h3 className="text-lg font-semibold mb-4">
                                    {METRIC_LABELS[selectedMetric]}
                                </h3>
                                <div className="space-y-3">
                                    {chartData
                                        .sort((a, b) => b.avg - a.avg)
                                        .map((d) => (
                                            <div key={d.model} className="flex items-center gap-4">
                                                <div className="w-40 text-sm truncate">{d.model}</div>
                                                <div className="flex-1 bg-gray-800 rounded-full h-8 relative overflow-hidden">
                                                    <div
                                                        className="bg-blue-500 h-full rounded-full flex items-center justify-end pr-2"
                                                        style={{
                                                            width: `${(d.avg / maxVal) * 100}%`,
                                                            minWidth: "2rem",
                                                        }}
                                                    >
                                                        <span className="text-xs font-mono text-white">
                                                            {d.avg.toFixed(1)}
                                                        </span>
                                                    </div>
                                                </div>
                                                <div className="text-xs text-gray-500 w-24 text-right">
                                                    n={d.count} · {d.min.toFixed(1)}–{d.max.toFixed(1)}
                                                </div>
                                            </div>
                                        ))}
                                </div>
                            </div>
                        )}

                        {filtered.length > 0 && (
                            <div className="bg-gray-900 rounded-lg p-6 overflow-x-auto">
                                <h3 className="text-lg font-semibold mb-4">Raw Data</h3>
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="text-gray-400 border-b border-gray-800">
                                            <th className="text-left py-2 px-3">Model</th>
                                            <th className="text-left py-2 px-3">Quant</th>
                                            <th className="text-left py-2 px-3">Chip</th>
                                            <th className="text-right py-2 px-3">Decode</th>
                                            <th className="text-right py-2 px-3">Prefill</th>
                                            <th className="text-right py-2 px-3">Memory</th>
                                            <th className="text-left py-2 px-3">Date</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {filtered.slice(0, 100).map((b) => (
                                            <tr
                                                key={b.id}
                                                className="border-b border-gray-800/50 hover:bg-gray-800/30"
                                            >
                                                <td className="py-2 px-3">{b.modelName}</td>
                                                <td className="py-2 px-3">{b.quantization}</td>
                                                <td className="py-2 px-3">{b.chipName}</td>
                                                <td className="text-right py-2 px-3">{b.tgTps.toFixed(1)}</td>
                                                <td className="text-right py-2 px-3">{b.ppTps.toFixed(1)}</td>
                                                <td className="text-right py-2 px-3">
                                                    {b.peakMemoryGb?.toFixed(1) ?? "–"}
                                                </td>
                                                <td className="py-2 px-3 text-gray-500">
                                                    {new Date(b.createdAt).toLocaleDateString()}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}

                        {chartData.length === 0 && !loading && (
                            <div className="bg-gray-900 rounded-lg p-12 text-center text-gray-500">
                                Select at least one model to compare
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
