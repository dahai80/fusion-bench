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

type SortKey = "tg_tps" | "pp_tps" | "ttft_ms" | "metric_value" | "context_length" | "created_at" | "model_name" | "chip_name";
type SortOrder = "asc" | "desc";

const BENCHMARK_TYPES = [
    { value: "", label: "All Types" },
    { value: "speed", label: "⚡ Speed" },
    { value: "accuracy", label: "🎯 Accuracy" },
    { value: "security", label: "🛡️ Security" },
    { value: "quant", label: "📊 Quant" },
    { value: "tune", label: "🔧 Tune" },
];

export default function BenchmarksPage() {
    const [data, setData] = useState<Benchmark[]>([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [limit] = useState(50);
    const [loading, setLoading] = useState(true);

    const [benchmarkType, setBenchmarkType] = useState("");
    const [chip, setChip] = useState("");
    const [model, setModel] = useState("");
    const [quant, setQuant] = useState("");
    const [sort, setSort] = useState<SortKey>("created_at");
    const [order, setOrder] = useState<SortOrder>("desc");

    const [chipOptions, setChipOptions] = useState<string[]>([]);
    const [modelOptions, setModelOptions] = useState<string[]>([]);
    const [quantOptions, setQuantOptions] = useState<string[]>([]);

    useEffect(() => {
        fetch("/api/benchmarks?limit=0")
            .then((r) => r.json())
            .then((res) => {
                const rows = res.data || [];
                const chips = [...new Set<string>(rows.map((b: Benchmark) => b.chipName))].sort();
                const models = [...new Set<string>(rows.map((b: Benchmark) => b.modelName))].sort();
                const quants = [...new Set<string>(rows.map((b: Benchmark) => b.quantization))].sort();
                setChipOptions(chips);
                setModelOptions(models);
                setQuantOptions(quants);
            })
            .catch(() => {});
    }, []);

    const fetchData = useCallback(async () => {
        setLoading(true);
        const params = new URLSearchParams({
            page: String(page),
            limit: String(limit),
            sort,
            order,
        });
        if (chip) params.set("chip", chip);
        if (model) params.set("model", model);
        if (quant) params.set("quant", quant);
        if (benchmarkType) params.set("benchmark_type", benchmarkType);

        try {
            const res = await fetch(`/api/benchmarks?${params}`);
            const json = await res.json();
            setData(json.data || []);
            setTotal(json.total || 0);
        } catch {
            setData([]);
            setTotal(0);
        } finally {
            setLoading(false);
        }
    }, [page, limit, sort, order, chip, model, quant, benchmarkType]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    const totalPages = Math.ceil(total / limit);

    const toggleSort = (key: SortKey) => {
        if (sort === key) {
            setOrder(order === "asc" ? "desc" : "asc");
        } else {
            setSort(key);
            setOrder(key === "model_name" || key === "chip_name" ? "asc" : "desc");
        }
        setPage(1);
    };

    const SortIcon = ({ col }: { col: SortKey }) => {
        if (sort !== col) return <span className="ml-1 text-neutral-300">↕</span>;
        return <span className="ml-1 text-neutral-900">{order === "asc" ? "↑" : "↓"}</span>;
    };

    const clearFilters = () => {
        setChip("");
        setModel("");
        setQuant("");
        setBenchmarkType("");
        setPage(1);
    };

    const isSpeedRow = (row: Benchmark) => (row.benchmarkType || "speed") === "speed";

    return (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-neutral-900">Benchmarks</h1>
                    <p className="mt-1 text-neutral-500">{total.toLocaleString()} results</p>
                </div>
                <Link
                    href="/get-started"
                    className="inline-flex items-center justify-center px-5 py-2.5 bg-neutral-900 text-white rounded-lg font-medium text-sm hover:bg-neutral-800 transition-colors"
                >
                    Submit Benchmark
                </Link>
            </div>

            {/* Filters */}
            <div className="flex flex-wrap gap-3 mb-6">
                <select
                    value={benchmarkType}
                    onChange={(e) => { setBenchmarkType(e.target.value); setPage(1); }}
                    className="px-3 py-2 rounded-lg border border-neutral-200 bg-white text-sm text-neutral-700 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent"
                >
                    {BENCHMARK_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                </select>
                <select
                    value={chip}
                    onChange={(e) => { setChip(e.target.value); setPage(1); }}
                    className="px-3 py-2 rounded-lg border border-neutral-200 bg-white text-sm text-neutral-700 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent"
                >
                    <option value="">All Chips</option>
                    {chipOptions.map((c) => (
                        <option key={c} value={c}>{c}</option>
                    ))}
                </select>
                <select
                    value={model}
                    onChange={(e) => { setModel(e.target.value); setPage(1); }}
                    className="px-3 py-2 rounded-lg border border-neutral-200 bg-white text-sm text-neutral-700 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent"
                >
                    <option value="">All Models</option>
                    {modelOptions.map((m) => (
                        <option key={m} value={m}>{m}</option>
                    ))}
                </select>
                <select
                    value={quant}
                    onChange={(e) => { setQuant(e.target.value); setPage(1); }}
                    className="px-3 py-2 rounded-lg border border-neutral-200 bg-white text-sm text-neutral-700 focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent"
                >
                    <option value="">All Quantizations</option>
                    {quantOptions.map((q) => (
                        <option key={q} value={q}>{q}</option>
                    ))}
                </select>
                {(chip || model || quant || benchmarkType) && (
                    <button
                        onClick={clearFilters}
                        className="px-3 py-2 rounded-lg border border-neutral-200 bg-white text-sm text-red-600 hover:bg-red-50 transition-colors"
                    >
                        Clear Filters
                    </button>
                )}
            </div>

            {/* Table */}
            <div className="bg-white rounded-2xl border border-neutral-200 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="bg-neutral-50 border-b border-neutral-200">
                                <th className="text-left px-4 py-3 font-medium text-neutral-500">Type</th>
                                <th className="text-left px-4 py-3 font-medium text-neutral-500">Task</th>
                                <th className="text-left px-4 py-3 font-medium text-neutral-500 cursor-pointer hover:text-neutral-900" onClick={() => toggleSort("model_name")}>
                                    Model <SortIcon col="model_name" />
                                </th>
                                <th className="text-left px-4 py-3 font-medium text-neutral-500">Quant</th>
                                <th className="text-left px-4 py-3 font-medium text-neutral-500 cursor-pointer hover:text-neutral-900" onClick={() => toggleSort("chip_name")}>
                                    Chip <SortIcon col="chip_name" />
                                </th>
                                <th className="text-right px-4 py-3 font-medium text-neutral-500 cursor-pointer hover:text-neutral-900" onClick={() => toggleSort("tg_tps")}>
                                    tg TPS <SortIcon col="tg_tps" />
                                </th>
                                <th className="text-right px-4 py-3 font-medium text-neutral-500 cursor-pointer hover:text-neutral-900" onClick={() => toggleSort("pp_tps")}>
                                    pp TPS <SortIcon col="pp_tps" />
                                </th>
                                <th className="text-right px-4 py-3 font-medium text-neutral-500">Metric</th>
                                <th className="text-right px-4 py-3 font-medium text-neutral-500 cursor-pointer hover:text-neutral-900" onClick={() => toggleSort("metric_value")}>
                                    Value <SortIcon col="metric_value" />
                                </th>
                                <th className="text-right px-4 py-3 font-medium text-neutral-500 cursor-pointer hover:text-neutral-900" onClick={() => toggleSort("created_at")}>
                                    Date <SortIcon col="created_at" />
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                <tr>
                                    <td colSpan={10} className="px-4 py-12 text-center text-neutral-400">Loading...</td>
                                </tr>
                            ) : data.length === 0 ? (
                                <tr>
                                    <td colSpan={10} className="px-4 py-12 text-center text-neutral-400">No benchmarks found</td>
                                </tr>
                            ) : (
                                data.map((row) => {
                                    const bType = row.benchmarkType || "speed";
                                    return (
                                        <tr key={row.id} className="border-b border-neutral-100 last:border-0 hover:bg-neutral-50">
                                            <td className="px-4 py-3">
                                                <span className="inline-flex px-2 py-0.5 rounded-md bg-neutral-900 text-white text-xs font-medium">
                                                    {bType}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 text-neutral-500 text-xs">{row.taskName || "—"}</td>
                                            <td className="px-4 py-3 font-medium text-neutral-900">
                                                <Link href={`/benchmarks/${row.id}`} className="hover:underline">{row.modelName}</Link>
                                            </td>
                                            <td className="px-4 py-3">
                                                <span className="inline-flex px-2 py-0.5 rounded-md bg-neutral-100 text-neutral-600 text-xs font-medium">{row.quantization}</span>
                                            </td>
                                            <td className="px-4 py-3 text-neutral-600">{row.chipName}</td>
                                            <td className="px-4 py-3 text-right font-mono tabular-nums text-neutral-900 font-medium">
                                                {isSpeedRow(row) ? row.tgTps.toFixed(1) : "—"}
                                            </td>
                                            <td className="px-4 py-3 text-right font-mono tabular-nums text-neutral-600">
                                                {isSpeedRow(row) ? row.ppTps.toFixed(1) : "—"}
                                            </td>
                                            <td className="px-4 py-3 text-right text-neutral-500 text-xs">{row.metricName || "decode_speed"}</td>
                                            <td className="px-4 py-3 text-right font-mono tabular-nums text-neutral-900 font-medium">
                                                {(row.metricValue ?? 0).toFixed(2)}
                                            </td>
                                            <td className="px-4 py-3 text-right text-neutral-400 text-xs">{new Date(row.createdAt).toLocaleDateString()}</td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="flex items-center justify-center gap-2 mt-6">
                    <button
                        onClick={() => setPage(Math.max(1, page - 1))}
                        disabled={page === 1}
                        className="px-3 py-2 rounded-lg border border-neutral-200 bg-white text-sm text-neutral-700 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-neutral-50"
                    >
                        Previous
                    </button>
                    <span className="px-4 py-2 text-sm text-neutral-500">
                        Page {page} of {totalPages}
                    </span>
                    <button
                        onClick={() => setPage(Math.min(totalPages, page + 1))}
                        disabled={page === totalPages}
                        className="px-3 py-2 rounded-lg border border-neutral-200 bg-white text-sm text-neutral-700 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-neutral-50"
                    >
                        Next
                    </button>
                </div>
            )}
        </div>
    );
}
