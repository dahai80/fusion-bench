import Link from "next/link";

export default function GetStartedPage() {
    return (
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
            <h1 className="text-3xl sm:text-4xl font-bold text-neutral-900 mb-4">Get Started</h1>
            <p className="text-lg text-neutral-600 mb-12">
                Run benchmarks on your Apple Silicon Mac and contribute to the community dataset.
            </p>

            {/* Step 1 */}
            <div className="mb-12">
                <div className="flex items-center gap-3 mb-4">
                    <span className="flex items-center justify-center w-8 h-8 rounded-full bg-neutral-900 text-white text-sm font-bold">1</span>
                    <h2 className="text-xl font-semibold text-neutral-900">Install fusion-mlx</h2>
                </div>
                <div className="ml-11 space-y-3">
                    <p className="text-neutral-600">
                        Install the fusion-mlx inference engine for Apple Silicon:
                    </p>
                    <CodeBlock command="pip install fusion-mlx" />
                </div>
            </div>

            {/* Step 2 */}
            <div className="mb-12">
                <div className="flex items-center gap-3 mb-4">
                    <span className="flex items-center justify-center w-8 h-8 rounded-full bg-neutral-900 text-white text-sm font-bold">2</span>
                    <h2 className="text-xl font-semibold text-neutral-900">Run the Server</h2>
                </div>
                <div className="ml-11 space-y-3">
                    <p className="text-neutral-600">
                        Start the fusion-mlx server with your chosen model:
                    </p>
                    <CodeBlock command="fusion-mlx serve --model Qwen3-4B --quantization Q4_K_M" />
                    <p className="text-neutral-600">
                        Or use the admin panel to browse and launch models:
                    </p>
                    <CodeBlock command="fusion-mlx serve --admin" />
                </div>
            </div>

            {/* Step 3 */}
            <div className="mb-12">
                <div className="flex items-center gap-3 mb-4">
                    <span className="flex items-center justify-center w-8 h-8 rounded-full bg-neutral-900 text-white text-sm font-bold">3</span>
                    <h2 className="text-xl font-semibold text-neutral-900">Submit Benchmarks</h2>
                </div>
                <div className="ml-11 space-y-3">
                    <p className="text-neutral-600">
                        Benchmarks run automatically when you use the admin panel. Results are
                        submitted to <code className="px-1.5 py-0.5 bg-neutral-100 rounded text-sm font-mono text-neutral-700">bench.dpdns.org</code> after each run.
                    </p>
                    <p className="text-neutral-600">
                        Each benchmark measures:
                    </p>
                    <ul className="list-disc list-inside text-neutral-600 space-y-1 ml-2">
                        <li><strong>tg TPS</strong> — Token generation throughput (tokens/sec)</li>
                        <li><strong>pp TPS</strong> — Prompt processing throughput (tokens/sec)</li>
                        <li><strong>TTFT</strong> — Time to first token (milliseconds)</li>
                        <li><strong>Peak Memory</strong> — Peak GPU memory usage (GB)</li>
                    </ul>
                </div>
            </div>

            {/* API Documentation */}
            <div className="mb-12">
                <h2 className="text-xl font-semibold text-neutral-900 mb-4">API Reference</h2>
                <div className="bg-neutral-900 rounded-2xl overflow-hidden">
                    <div className="flex items-center gap-2 px-4 py-3 border-b border-neutral-700">
                        <span className="px-2 py-0.5 bg-green-600 text-white text-xs font-bold rounded">POST</span>
                        <code className="text-neutral-300 text-sm font-mono">/api/benchmarks</code>
                    </div>
                    <div className="p-4 overflow-x-auto">
                        <pre className="text-sm font-mono text-neutral-300 leading-relaxed">{`{
  "chip_name": "M2 Ultra",
  "chip_variant": "",
  "memory_gb": 192,
  "gpu_cores": 76,
  "os_version": "macOS 15.3",
  "omlx_version": "0.9.8",
  "model_name": "Qwen3-32B",
  "quantization": "Q4_K_M",
  "context_length": 4096,
  "pp_tps": 128.5,
  "tg_tps": 24.3,
  "ttft_ms": 320.1,
  "peak_memory_gb": 18.2,
  "submission_group": "uuid-string",
  "owner_hash": "optional-anonymous-id",
  "batching_results": []
}`}</pre>
                    </div>
                </div>

                <div className="mt-4 grid sm:grid-cols-2 gap-4">
                    <div className="p-5 rounded-xl bg-green-50 border border-green-200">
                        <div className="flex items-center gap-2 mb-2">
                            <span className="flex items-center justify-center w-6 h-6 rounded-full bg-green-600 text-white">
                                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="white" strokeWidth="2">
                                    <path d="M3 7l3 3 5-5" strokeLinecap="round" strokeLinejoin="round" />
                                </svg>
                            </span>
                            <p className="text-sm font-semibold text-green-800">201 Created</p>
                        </div>
                        <p className="text-sm text-green-700 mb-2">Benchmark saved successfully.</p>
                        <div className="flex items-center gap-2 text-sm text-green-600">
                            <span>View at</span>
                            <code className="px-1.5 py-0.5 bg-green-100 rounded font-mono">/benchmarks/42</code>
                        </div>
                    </div>
                    <div className="p-5 rounded-xl bg-amber-50 border border-amber-200">
                        <div className="flex items-center gap-2 mb-2">
                            <span className="flex items-center justify-center w-6 h-6 rounded-full bg-amber-500 text-white">
                                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="white" strokeWidth="2">
                                    <path d="M7 4v4M7 10.5v.5" strokeLinecap="round" />
                                </svg>
                            </span>
                            <p className="text-sm font-semibold text-amber-800">409 Duplicate</p>
                        </div>
                        <p className="text-sm text-amber-700 mb-2">Same chip + model + quant + context already exists.</p>
                        <div className="flex items-center gap-2 text-sm text-amber-600">
                            <span>Existing at</span>
                            <code className="px-1.5 py-0.5 bg-amber-100 rounded font-mono">/benchmarks/42</code>
                        </div>
                    </div>
                </div>
            </div>

            {/* Owner Hash */}
            <div className="mb-12">
                <h2 className="text-xl font-semibold text-neutral-900 mb-4">Owner Hash</h2>
                <div className="p-6 rounded-2xl border border-neutral-200 bg-neutral-50">
                    <p className="text-neutral-600 leading-relaxed mb-4">
                        The <code className="px-1.5 py-0.5 bg-white rounded text-sm font-mono text-neutral-700 border border-neutral-200">owner_hash</code> field is an optional anonymous identifier.
                        It allows you to:
                    </p>
                    <ul className="list-disc list-inside text-neutral-600 space-y-2 ml-2">
                        <li>View all your submissions at <code className="px-1.5 py-0.5 bg-white rounded text-sm font-mono text-neutral-700 border border-neutral-200">/my/{`{your_hash}`}</code></li>
                        <li>Deduplicate submissions — same owner + model + chip + quant + context = skipped</li>
                        <li>Track your contribution history without creating an account</li>
                    </ul>
                    <p className="text-neutral-500 text-sm mt-4">
                        Generate one with: <code className="px-1.5 py-0.5 bg-white rounded text-sm font-mono text-neutral-700 border border-neutral-200">python -c &quot;import uuid; print(uuid.uuid4().hex[:16])&quot;</code>
                    </p>
                </div>
            </div>

            <div className="text-center pt-8 border-t border-neutral-200">
                <Link
                    href="/benchmarks"
                    className="inline-flex items-center justify-center px-8 py-3.5 bg-neutral-900 text-white rounded-xl font-medium text-base hover:bg-neutral-800 transition-colors"
                >
                    View Community Benchmarks
                </Link>
            </div>
        </div>
    );
}

function CodeBlock({ command }: { command: string }) {
    return (
        <div className="flex items-center gap-2 bg-neutral-900 rounded-xl px-4 py-3">
            <span className="text-neutral-500 font-mono text-sm">$</span>
            <code className="text-neutral-100 font-mono text-sm flex-1">{command}</code>
        </div>
    );
}
