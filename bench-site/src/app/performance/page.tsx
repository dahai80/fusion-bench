"use client";

import { useState, useEffect, useCallback } from "react";
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Legend,
} from "recharts";

type GroupBy = "model" | "chip" | "quant" | "type" | "task";
type Metric = "tg_tps" | "pp_tps" | "ttft_ms" | "metric_value";

interface AggRow {
    key: string;
    avg: number;
    max: number;
    min: number;
    count: number;
}

const METRIC_LABELS: Record<Metric, string> = {
    tg_tps: "Token Generation (tok/s)",
    pp_tps: "Prompt Processing (tok/s)",
    ttft_ms: "Time to First Token (ms)",
    metric_value: "Metric Value",
};

const GROUP_LABELS: Record<GroupBy, string> = {
    model: "Model",
    chip: "Chip",
    quant: "Quantization",
    type: "Benchmark Type",
    task: "Task",
};

const BENCHMARK_TYPES = [
    { value: "", label: "All Types" },
    { value: "speed", label: "⚡ Speed" },
    { value: "accuracy", label: "🎯 Accuracy" },
    { value: "security", label: "🛡️ Security" },
    { value: "quant", label: "📊 Quant" },
    { value: "tune", label: "🔧 Tune" },
];

export default function PerformancePage() {
    const [data, setData] = useState<AggRow[]>([]);
    const [loading, setLoading] = useState(true);

    const [groupBy, setGroupBy] = useState<GroupBy>("model");
    const [metric, setMetric] = useState<Metric>("tg_tps");
    const [chip, setChip] = useState("");
    const [quant, setQuant] = useState("");
    const [benchmarkType, setBenchmarkType] = useState("");

    const [chipOptions, setChipOptions] = useState<string[]>([]);
    const [quantOptions, setQuantOptions] = useState<string[]>([]);

    useEffect(() => {
        fetch("/api/benchmarks?limit=0")
            .then((r) => r.json())
            .then((res) => {
                const rows = res.data || [];
                setChipOptions([...new Set<string>(rows.map((b: { chipName: string }) => b.chipName))].sort());
                setQuantOptions([...new Set<string>(rows.map((b: { quantization: string }) => b.quantization))].sort());
            })
            .catch(() => {});
    }, []);

    const fetchData = useCallback(async () => {
        setLoading(true);
        const params = new URLSearchParams({ group_by: groupBy, metric });
        if (chip) params.set("chip", chip);
        if (quant) params.set("quant", quant);
        if (benchmarkType) params.set("benchmark_type", benchmarkType);

        try {
            const res = await fetch(`/api/benchmarks/aggregate?${params}`);
            const json = await res.json();
            setData(json.groups || []);
        } catch {
            setData([]);
        } finally {
            setLoading(false);
        }
    }, [groupBy, metric, chip, quant, benchmarkType]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    const isAscMetric = metric === "ttft_ms";

    const chartData = data
        .filter((d) => d.count > 0)
        .sort((a, b) => isAscMetric ? a.avg - b.avg : b.avg - a.avg)
        .slice(0, 30);

    const bestLabel = isAscMetric ? "min" : "max";
    const worstLabel = isAscMetric ? "max" : "min";

    const barColor = metric === "ttft_ms" ? "#f59e0b" : metric === "metric_value" ? "#3b82f6" : "#171717";
    const maxColor = metric === "ttft_ms" ? "#fbbf24" : metric === "metric_value" ? "#93c5fd" : "#525252";

    const handleMetricChange = (m: Metric) => {
        setMetric(m);
        if (m === "metric_value" && groupBy === "model") {
            setGroupBy("type");
        }
    };

    const handleTypeChange = (t: string) => {
        setBenchmarkType(t);
        if (t === "speed") {
            setMetric("tg_tps");
        } else if (t) {
            setMetric("metric_value");
        }
    };

    const clearFilters = () => {
        setChip("");
        setQuant("");
        setBenchmarkType("");
        setMetric("tg_tps");
        setGroupBy("model");
    };

    return (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
            <h1 className="text-3xl font-bold text-neutral-900 mb-2">Performance Explorer</h1>
            <p className="text-neutral-500 mb-8">
                Compare {GROUP_LABELS[groupBy].toLowerCase()} performance across Apple Silicon
            </p>

            {/* Controls */}
            <div className="flex flex-wrap gap-3 mb-8">
                <select
                    value={benchmarkType}
                    onChange={(e) => handleTypeChange(e.target.value)}
                    className="px-3 py-2 rounded-lg border border-neutral-200 bg-white text-sm text-neutral-700 focus:outline-none focus:ring-2 focus:ring-neutral-900"
                >
                    {BENCHMARK_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                </select>
                <select
                    value={groupBy}
                    onChange={(e) => setGroupBy(e.target.value as GroupBy)}
                    className="px-3 py-2 rounded-lg border border-neutral-200 bg-white text-sm text-neutral-700 focus:outline-none focus:ring-2 focus:ring-neutral-900"
                >
                    <option value="model">Group by Model</option>
                    <option value="chip">Group by Chip</option>
                    <option value="quant">Group by Quantization</option>
                    <option value="type">Group by Type</option>
                    <option value="task">Group by Task</option>
                </select>
                <select
                    value={metric}
                    onChange={(e) => handleMetricChange(e.target.value as Metric)}
                    className="px-3 py-2 rounded-lg border border-neutral-200 bg-white text-sm text-neutral-700 focus:outline-none focus:ring-2 focus:ring-neutral-900"
                >
                    <option value="tg_tps">Token Generation (tok/s)</option>
                    <option value="pp_tps">Prompt Processing (tok/s)</option>
                    <option value="ttft_ms">Time to First Token (ms)</option>
                    <option value="metric_value">Metric Value (universal)</option>
                </select>
                <select
                    value={chip}
                    onChange={(e) => setChip(e.target.value)}
                    className="px-3 py-2 rounded-lg border border-neutral-200 bg-white text-sm text-neutral-700 focus:outline-none focus:ring-2 focus:ring-neutral-900"
                >
                    <option value="">All Chips</option>
                    {chipOptions.map((c) => (
                        <option key={c} value={c}>{c}</option>
                    ))}
                </select>
                <select
                    value={quant}
                    onChange={(e) => setQuant(e.target.value)}
                    className="px-3 py-2 rounded-lg border border-neutral-200 bg-white text-sm text-neutral-700 focus:outline-none focus:ring-2 focus:ring-neutral-900"
                >
                    <option value="">All Quantizations</option>
                    {quantOptions.map((q) => (
                        <option key={q} value={q}>{q}</option>
                    ))}
                </select>
                {(chip || quant || benchmarkType) && (
                    <button
                        onClick={clearFilters}
                        className="px-3 py-2 rounded-lg border border-neutral-200 bg-white text-sm text-red-600 hover:bg-red-50 transition-colors"
                    >
                        Clear Filters
                    </button>
                )}
            </div>

            {/* Chart */}
            <div className="bg-white rounded-2xl border border-neutral-200 p-6 mb-8">
                {loading ? (
                    <div className="h-96 flex items-center justify-center text-neutral-400">Loading...</div>
                ) : chartData.length === 0 ? (
                    <div className="h-96 flex items-center justify-center text-neutral-400">
                        No data available. Submit benchmarks to see charts.
                    </div>
                ) : (
                    <ResponsiveContainer width="100%" height={480}>
                        <BarChart data={chartData} margin={{ top: 8, right: 8, left: 8, bottom: 80 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                            <XAxis
                                dataKey="key"
                                angle={-45}
                                textAnchor="end"
                                interval={0}
                                tick={{ fontSize: 11, fill: "#737373" }}
                                height={80}
                            />
                            <YAxis
                                tick={{ fontSize: 12, fill: "#737373" }}
                                label={{
                                    value: METRIC_LABELS[metric],
                                    angle: -90,
                                    position: "insideLeft",
                                    style: { fill: "#737373", fontSize: 12 },
                                }}
                            />
                            <Tooltip
                                contentStyle={{
                                    borderRadius: "12px",
                                    border: "1px solid #e5e5e5",
                                    fontSize: "13px",
                                }}
                                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                                formatter={(value: any, name: any) => {
                                    const v = typeof value === "number" ? value.toFixed(2) : String(value);
                                    return [v, name === "avg" ? "Average" : name === bestLabel ? "Best" : "Worst"];
                                }}
                            />
                            <Legend
                                formatter={(value: string) => (value === "avg" ? "Average" : "Best")}
                            />
                            <Bar dataKey="avg" fill={barColor} radius={[4, 4, 0, 0]} name="avg" />
                            <Bar dataKey="max" fill={maxColor} radius={[4, 4, 0, 0]} name="max" opacity={0.5} />
                        </BarChart>
                    </ResponsiveContainer>
                )}
            </div>

            {/* Summary Table */}
            {chartData.length > 0 && (
                <div className="bg-white rounded-2xl border border-neutral-200 overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="bg-neutral-50 border-b border-neutral-200">
                                    <th className="text-left px-4 py-3 font-medium text-neutral-500">{GROUP_LABELS[groupBy]}</th>
                                    <th className="text-right px-4 py-3 font-medium text-neutral-500">Average</th>
                                    <th className="text-right px-4 py-3 font-medium text-neutral-500">Best</th>
                                    <th className="text-right px-4 py-3 font-medium text-neutral-500">Worst</th>
                                    <th className="text-right px-4 py-3 font-medium text-neutral-500">Submissions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {chartData.map((row) => (
                                    <tr key={row.key} className="border-b border-neutral-100 last:border-0 hover:bg-neutral-50">
                                        <td className="px-4 py-3 font-medium text-neutral-900">{row.key}</td>
                                        <td className="px-4 py-3 text-right font-mono tabular-nums text-neutral-900">{row.avg.toFixed(2)}</td>
                                        <td className="px-4 py-3 text-right font-mono tabular-nums text-green-600">{row[bestLabel].toFixed(2)}</td>
                                        <td className="px-4 py-3 text-right font-mono tabular-nums text-neutral-500">{row[worstLabel].toFixed(2)}</td>
                                        <td className="px-4 py-3 text-right text-neutral-500">{row.count}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
}
