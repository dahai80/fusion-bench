import { getDb } from "@/db";
import { benchmarks } from "@/db/schema";
import { eq, desc } from "drizzle-orm";
import Link from "next/link";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function MyBenchmarksPage({ params }: { params: Promise<{ hash: string }> }) {
    const { hash } = await params;
    if (!hash || hash.length > 128 || !/^[a-zA-Z0-9_-]+$/.test(hash)) notFound();
    const db = getDb();
    const rows = await db
        .select()
        .from(benchmarks)
        .where(eq(benchmarks.ownerHash, hash))
        .orderBy(desc(benchmarks.createdAt));

    return (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
            <div className="mb-8">
                <Link href="/benchmarks" className="text-sm text-neutral-500 hover:text-neutral-900 transition-colors">
                    ← Back to Benchmarks
                </Link>
                <h1 className="text-3xl font-bold text-neutral-900 mt-2">My Submissions</h1>
                <p className="mt-1 text-neutral-500">
                    Owner: <code className="px-1.5 py-0.5 bg-neutral-100 rounded text-sm font-mono text-neutral-700">{hash}</code>
                    {" "}({rows.length} results)
                </p>
            </div>

            {rows.length === 0 ? (
                <div className="text-center py-16">
                    <p className="text-neutral-400 text-lg">No submissions found for this owner hash.</p>
                    <Link href="/get-started" className="mt-4 inline-block text-neutral-900 font-medium hover:underline">
                        Get Started →
                    </Link>
                </div>
            ) : (
                <div className="bg-white rounded-2xl border border-neutral-200 overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="bg-neutral-50 border-b border-neutral-200">
                                    <th className="text-left px-4 py-3 font-medium text-neutral-500">Model</th>
                                    <th className="text-left px-4 py-3 font-medium text-neutral-500">Quant</th>
                                    <th className="text-left px-4 py-3 font-medium text-neutral-500">Chip</th>
                                    <th className="text-left px-4 py-3 font-medium text-neutral-500">Memory</th>
                                    <th className="text-right px-4 py-3 font-medium text-neutral-500">Context</th>
                                    <th className="text-right px-4 py-3 font-medium text-neutral-500">tg TPS</th>
                                    <th className="text-right px-4 py-3 font-medium text-neutral-500">pp TPS</th>
                                    <th className="text-right px-4 py-3 font-medium text-neutral-500">TTFT</th>
                                    <th className="text-right px-4 py-3 font-medium text-neutral-500">Date</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((row) => (
                                    <tr key={row.id} className="border-b border-neutral-100 last:border-0 hover:bg-neutral-50">
                                        <td className="px-4 py-3 font-medium text-neutral-900">{row.modelName}</td>
                                        <td className="px-4 py-3">
                                            <span className="inline-flex px-2 py-0.5 rounded-md bg-neutral-100 text-neutral-600 text-xs font-medium">{row.quantization}</span>
                                        </td>
                                        <td className="px-4 py-3 text-neutral-600">{row.chipName}</td>
                                        <td className="px-4 py-3 text-neutral-600">{row.memoryGb} GB</td>
                                        <td className="px-4 py-3 text-right text-neutral-500">{row.contextLength.toLocaleString()}</td>
                                        <td className="px-4 py-3 text-right font-mono tabular-nums text-neutral-900 font-medium">{row.tgTps.toFixed(1)}</td>
                                        <td className="px-4 py-3 text-right font-mono tabular-nums text-neutral-600">{row.ppTps.toFixed(1)}</td>
                                        <td className="px-4 py-3 text-right font-mono tabular-nums text-neutral-600">{row.ttftMs?.toFixed(0) ?? "—"}</td>
                                        <td className="px-4 py-3 text-right text-neutral-400 text-xs">{new Date(row.createdAt).toLocaleDateString()}</td>
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
