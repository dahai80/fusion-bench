import Link from "next/link";
import { getDb } from "@/db";
import { benchmarks } from "@/db/schema";
import { desc, sql } from "drizzle-orm";
import ArchitectureDiagram from "./components/architecture-diagram";

export const dynamic = "force-dynamic";

const TYPE_LABELS: Record<string, string> = {
    speed: "⚡ Speed",
    accuracy: "🎯 Accuracy",
    security: "🛡️ Security",
    quant: "📊 Quant",
    tune: "🔧 Tune",
};

export default async function HomePage() {
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

    const totalSubmissions = totalResult[0]?.count ?? 0;
    const totalChips = chipResult[0]?.count ?? 0;
    const totalModels = modelResult[0]?.count ?? 0;
    const byType: Record<string, number> = {};
    for (const r of typeResult) {
        byType[r.type] = r.count;
    }

    return (
        <div>
            {/* Hero */}
            <section className="relative overflow-hidden bg-gradient-to-b from-neutral-50 to-white">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24 sm:py-32">
                    <div className="text-center max-w-3xl mx-auto">
                        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-neutral-900 tracking-tight">
                            Apple Silicon
                            <span className="block mt-2 bg-gradient-to-r from-neutral-900 to-neutral-500 bg-clip-text text-transparent">
                                LLM Benchmarks
                            </span>
                        </h1>
                        <p className="mt-6 text-lg sm:text-xl text-neutral-600 leading-relaxed">
                            Speed, accuracy, security, quant &amp; tuning benchmarks for Apple Silicon.
                            Run locally, submit results, explore community data.
                        </p>
                        <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center">
                            <Link
                                href="/benchmarks"
                                className="inline-flex items-center justify-center px-8 py-3.5 bg-neutral-900 text-white rounded-xl font-medium text-base hover:bg-neutral-800 transition-colors shadow-lg shadow-neutral-900/20"
                            >
                                Explore Benchmarks
                            </Link>
                            <Link
                                href="/get-started"
                                className="inline-flex items-center justify-center px-8 py-3.5 bg-white text-neutral-700 rounded-xl font-medium text-base border border-neutral-200 hover:bg-neutral-50 transition-colors"
                            >
                                Get Started
                            </Link>
                        </div>
                    </div>
                </div>
            </section>

            {/* Architecture Diagram */}
            <ArchitectureDiagram />

            {/* Stats */}
            <section className="border-y border-neutral-200 bg-white">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
                    <div className="grid grid-cols-3 gap-8 text-center">
                        <div>
                            <p className="text-3xl sm:text-4xl font-bold text-neutral-900">{totalSubmissions.toLocaleString()}</p>
                            <p className="mt-1 text-sm text-neutral-500">Submissions</p>
                        </div>
                        <div>
                            <p className="text-3xl sm:text-4xl font-bold text-neutral-900">{totalChips}</p>
                            <p className="mt-1 text-sm text-neutral-500">Chip Variants</p>
                        </div>
                        <div>
                            <p className="text-3xl sm:text-4xl font-bold text-neutral-900">{totalModels}</p>
                            <p className="mt-1 text-sm text-neutral-500">Models Tested</p>
                        </div>
                    </div>
                    {/* Type distribution */}
                    {Object.keys(byType).length > 0 && (
                        <div className="mt-8 flex flex-wrap justify-center gap-3">
                            {Object.entries(byType).map(([type, count]) => (
                                <Link
                                    key={type}
                                    href={`/benchmarks?benchmark_type=${type}`}
                                    className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-neutral-50 border border-neutral-200 text-sm text-neutral-700 hover:bg-neutral-100 transition-colors"
                                >
                                    <span>{TYPE_LABELS[type] || type}</span>
                                    <span className="font-mono tabular-nums text-neutral-500">{count}</span>
                                </Link>
                            ))}
                        </div>
                    )}
                </div>
            </section>

            {/* Feature Cards */}
            <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
                <div className="grid md:grid-cols-5 gap-6">
                    <FeatureCard
                        icon="⚡"
                        title="Speed"
                        description="Token generation, prompt processing, TTFT, and memory benchmarks."
                    />
                    <FeatureCard
                        icon="🎯"
                        title="Accuracy"
                        description="MMLU, GSM8K and other lm-eval-harness task accuracy."
                    />
                    <FeatureCard
                        icon="🛡️"
                        title="Security"
                        description="Injection, harmful content, and PII leak safety probes."
                    />
                    <FeatureCard
                        icon="📊"
                        title="Quantization"
                        description="Multi-quant level speed and stability comparison."
                    />
                    <FeatureCard
                        icon="🔧"
                        title="Tuning"
                        description="Auto-tuning batch size, max tokens, and temperature."
                    />
                </div>
            </section>

            {/* Latest Submissions */}
            {latestResult.length > 0 && (
                <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-20">
                    <h2 className="text-2xl font-bold text-neutral-900 mb-6">Latest Submissions</h2>
                    <div className="bg-white rounded-2xl border border-neutral-200 overflow-hidden">
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="bg-neutral-50 border-b border-neutral-200">
                                        <th className="text-left px-4 py-3 font-medium text-neutral-500">Type</th>
                                        <th className="text-left px-4 py-3 font-medium text-neutral-500">Model</th>
                                        <th className="text-left px-4 py-3 font-medium text-neutral-500">Quant</th>
                                        <th className="text-left px-4 py-3 font-medium text-neutral-500">Chip</th>
                                        <th className="text-right px-4 py-3 font-medium text-neutral-500">Metric</th>
                                        <th className="text-right px-4 py-3 font-medium text-neutral-500">Value</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {latestResult.map((row) => (
                                        <tr key={row.id} className="border-b border-neutral-100 last:border-0 hover:bg-neutral-50">
                                            <td className="px-4 py-3">
                                                <span className="inline-flex px-2 py-0.5 rounded-md bg-neutral-900 text-white text-xs font-medium">
                                                    {row.benchmarkType || "speed"}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 font-medium text-neutral-900">{row.modelName}</td>
                                            <td className="px-4 py-3">
                                                <span className="inline-flex px-2 py-0.5 rounded-md bg-neutral-100 text-neutral-600 text-xs font-medium">{row.quantization}</span>
                                            </td>
                                            <td className="px-4 py-3 text-neutral-600">{row.chipName}</td>
                                            <td className="px-4 py-3 text-right text-neutral-500 text-xs">{row.metricName || "decode_speed"}</td>
                                            <td className="px-4 py-3 text-right font-mono tabular-nums text-neutral-900 font-medium">
                                                {(row.metricValue ?? row.tgTps).toFixed(2)}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </section>
            )}
        </div>
    );
}

function FeatureCard({ icon, title, description }: { icon: string; title: string; description: string }) {
    return (
        <div className="p-5 rounded-2xl border border-neutral-200 bg-white hover:shadow-md transition-shadow">
            <div className="text-2xl mb-3">{icon}</div>
            <h3 className="text-base font-semibold text-neutral-900 mb-1">{title}</h3>
            <p className="text-neutral-600 text-sm leading-relaxed">{description}</p>
        </div>
    );
}
