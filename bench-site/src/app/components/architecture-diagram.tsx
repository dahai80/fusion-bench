export default function ArchitectureDiagram() {
    const isLive = (name: string) => ["bench.dpdns.org", "macOS App", "Fusion-Code", "Fusion-MLX", "Fusion-Multi-Node", "Fusion-Artifacts", "Fusion-Model\nHub", "MLX", "MLX-LM", "MLX-VLM"].includes(name);
    const liveHref = (name: string) =>
        name === "Fusion-Code" ? "https://github.com/dahai80/fusion-code"
        : name === "Fusion-Multi-Node" ? "https://github.com/dahai80/fusion-multi-nodes"
        : name === "Fusion-Artifacts" ? "https://github.com/dahai80/fusion-artifacts-engine"
        : name === "Fusion-Model\nHub" ? "https://github.com/dahai80/fusion-models-hub"
        : "https://github.com/dahai80/fusion-mlx";

    return (
        <section className="bg-white py-1">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="text-center mb-1">
                    <h2 className="text-lg sm:text-xl font-bold text-neutral-900 tracking-tight">
                        Fusion Architecture Overview
                    </h2>
                    <p className="mt-0.5 text-xs text-neutral-500 max-w-2xl mx-auto">
                        From hardware to applications, building a complete Apple Silicon AI infrastructure
                    </p>
                    <div className="flex items-center justify-center gap-2 mt-1 text-[9px] text-neutral-500">
                        <span className="inline-flex items-center gap-0.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                            Live
                        </span>
                        <span className="inline-flex items-center gap-0.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-neutral-300" />
                            Future
                        </span>
                    </div>
                </div>

                <div className="relative">
                    {/* Layer 6: Portal */}
                    <div className="relative z-10 mb-0.5">
                        <div className="text-center mb-0.5">
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-neutral-100 text-neutral-600 text-[9px] font-medium tracking-wider uppercase">
                                Portal
                            </span>
                        </div>
                        <div className="grid grid-cols-2 gap-1">
                            {[
                                { name: "bench.dpdns.org", desc: "Web Portal" },
                                { name: "macOS App", desc: "Desktop App" },
                            ].map((item) => (
                                isLive(item.name)
                                    ? (
                                        <a key={item.name} href={item.name === "bench.dpdns.org" ? "https://bench.dpdns.org" : "https://github.com/dahai80/fusion-mlx/releases"}
                                            target="_blank" rel="noopener noreferrer"
                                            className="bg-white border-2 border-neutral-900 rounded py-1 px-1.5 text-center hover:bg-neutral-50 transition-all duration-300"
                                        >
                                            <div className="flex items-center justify-center gap-0.5">
                                                <span className="w-1 h-1 rounded-full bg-emerald-500" />
                                                <span className="text-xs font-semibold text-neutral-900">{item.name}</span>
                                            </div>
                                            <div className="text-[9px] text-neutral-500 leading-tight">{item.desc}</div>
                                        </a>
                                    ) : (
                                        <div key={item.name} className="bg-white border border-dashed border-neutral-200 rounded py-1 px-1.5 text-center">
                                            <div className="flex items-center justify-center gap-0.5">
                                                <span className="w-1 h-1 rounded-full bg-neutral-300" />
                                                <span className="text-xs font-semibold text-neutral-400">{item.name}</span>
                                            </div>
                                            <div className="text-[7px] text-neutral-300 leading-tight">{item.desc}</div>
                                        </div>
                                    )
                            ))}
                        </div>
                    </div>

                    {/* Layer 5: Applications */}
                    <div className="relative z-10 mb-0.5">
                        <div className="text-center mb-0.5">
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-neutral-100 text-neutral-600 text-[9px] font-medium tracking-wider uppercase">
                                Applications
                            </span>
                        </div>
                        <div className="grid grid-cols-5 gap-1">
                            {[
                                { name: "Fusion-K12\nTeacher", desc: "Smart Education" },
                                { name: "Fusion-Finance", desc: "Financial Analysis" },
                                { name: "Fusion-Health", desc: "Healthcare" },
                                { name: "Fusion-Ecommerce", desc: "E-commerce Platform" },
                                { name: "Fusion-Science", desc: "Scientific Computing" },
                            ].map((item) => (
                                <div key={item.name} className="bg-white border border-dashed border-neutral-200 rounded py-0.5 px-1 text-center">
                                    <div className="flex items-center justify-center gap-0.5">
                                        <span className="w-1 h-1 rounded-full bg-neutral-300 shrink-0" />
                                        <span className="text-[10px] font-semibold text-neutral-400 whitespace-pre-line leading-tight">{item.name}</span>
                                    </div>
                                    <div className="text-[9px] text-neutral-300 leading-tight">{item.desc}</div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Layer 4: Ecosystem */}
                    <div className="relative z-10 mb-0.5">
                        <div className="text-center mb-0.5">
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-neutral-100 text-neutral-600 text-[9px] font-medium tracking-wider uppercase">
                                Ecosystem
                            </span>
                        </div>
                        <div className="grid grid-cols-4 gap-1">
                            {[
                                { name: "Fusion-Plugins\nEcosystem", desc: "Plugin Ecosystem" },
                                { name: "Fusion-Bench", desc: "Performance Benchmarking" },
                                { name: "Fusion-Browser", desc: "Browser Engine" },
                                { name: "Fusion-Skills", desc: "Skills Library" },
                                { name: "Fusion-Simulation", desc: "Simulation" },
                                { name: "Fusion-Robot", desc: "Robot Control" },
                                { name: "Fusion-ComfyUI", desc: "ComfyUI Workflow" },
                            ].map((item) => (
                                <div key={item.name} className="bg-white border border-dashed border-neutral-200 rounded py-0.5 px-1 text-center">
                                    <div className="flex items-center justify-center gap-0.5">
                                        <span className="w-1 h-1 rounded-full bg-neutral-300 shrink-0" />
                                        <span className="text-[10px] font-semibold text-neutral-400 whitespace-pre-line leading-tight">{item.name}</span>
                                    </div>
                                    <div className="text-[9px] text-neutral-300 leading-tight">{item.desc}</div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Layer 3: Developer Tools */}
                    <div className="relative z-10 mb-0.5">
                        <div className="text-center mb-0.5">
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-neutral-100 text-neutral-600 text-[9px] font-medium tracking-wider uppercase">
                                Developer Tools
                            </span>
                        </div>
                        <div className="grid grid-cols-4 gap-1">
                            {[
                                { name: "Fusion-Doc", desc: "Smart Documentation" },
                                { name: "Fusion-Code", desc: "Code Generation" },
                                { name: "Fusion-Design", desc: "Design Tools" },
                                { name: "Fusion-Security", desc: "Security Audit" },
                                { name: "Fusion-Desk", desc: "Desktop Assistant" },
                                { name: "Fusion-Agent\nStudio", desc: "Agent Studio" },
                                { name: "Fusion-CLI", desc: "CLI Tools" },
                                { name: "Fusion-Code\nModernization", desc: "Code Modernization" },
                            ].map((item) =>
                                isLive(item.name) ? (
                                    <a key={item.name}
                                        href={liveHref(item.name)}
                                        target="_blank" rel="noopener noreferrer"
                                        className="bg-white border-2 border-neutral-900 rounded py-0.5 px-1 text-center hover:bg-neutral-50 transition-all duration-300"
                                    >
                                        <div className="flex items-center justify-center gap-0.5">
                                            <span className="w-1 h-1 rounded-full bg-emerald-500 shrink-0" />
                                            <span className="text-[10px] font-semibold text-neutral-900 whitespace-pre-line leading-tight">{item.name}</span>
                                        </div>
                                        <div className="text-[9px] text-neutral-500 leading-tight">{item.desc}</div>
                                    </a>
                                ) : (
                                    <div key={item.name} className="bg-white border border-dashed border-neutral-200 rounded py-0.5 px-1 text-center">
                                        <div className="flex items-center justify-center gap-0.5">
                                            <span className="w-1 h-1 rounded-full bg-neutral-300 shrink-0" />
                                            <span className="text-[10px] font-semibold text-neutral-400 whitespace-pre-line leading-tight">{item.name}</span>
                                        </div>
                                        <div className="text-[9px] text-neutral-300 leading-tight">{item.desc}</div>
                                    </div>
                                )
                            )}
                        </div>
                    </div>

                    {/* Layer 2: Core Framework */}
                    <div className="relative z-10 mb-0.5">
                        <div className="text-center mb-0.5">
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-neutral-100 text-neutral-600 text-[9px] font-medium tracking-wider uppercase">
                                Core Framework
                            </span>
                        </div>
                        <div className="grid grid-cols-4 gap-1">
                            {[
                                { name: "Fusion-MLX", desc: "MLX Inference Engine" },
                                { name: "Fusion-Model\nHub", desc: "Model Hub" },
                                { name: "Fusion-Artifacts", desc: "Artifacts Engine" },
                                { name: "Fusion-Multi-Node", desc: "Multi-Node Orchestration" },
                            ].map((item) => (
                                isLive(item.name)
                                    ? (
                                        <a key={item.name} href={liveHref(item.name)}
                                            target="_blank" rel="noopener noreferrer"
                                            className="bg-white border-2 border-neutral-900 rounded py-0.5 px-1 text-center hover:bg-neutral-50 transition-all duration-300"
                                        >
                                            <div className="flex items-center justify-center gap-0.5">
                                                <span className="w-1 h-1 rounded-full bg-emerald-500 shrink-0" />
                                                <span className="text-[10px] font-semibold text-neutral-900 whitespace-pre-line leading-tight">{item.name}</span>
                                            </div>
                                            <div className="text-[9px] text-neutral-500 leading-tight">{item.desc}</div>
                                        </a>
                                    ) : (
                                        <div key={item.name} className="bg-white border border-dashed border-neutral-200 rounded py-0.5 px-1 text-center">
                                            <div className="flex items-center justify-center gap-0.5">
                                                <span className="w-1 h-1 rounded-full bg-neutral-300 shrink-0" />
                                                <span className="text-[10px] font-semibold text-neutral-400 whitespace-pre-line leading-tight">{item.name}</span>
                                            </div>
                                            <div className="text-[9px] text-neutral-300 leading-tight">{item.desc}</div>
                                        </div>
                                    )
                            ))}
                        </div>
                    </div>

                    {/* Layer 1: Infrastructure */}
                    <div className="relative z-10">
                        <div className="text-center mb-0.5">
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-neutral-100 text-neutral-600 text-[9px] font-medium tracking-wider uppercase">
                                Infrastructure
                            </span>
                        </div>
                        <div className="grid grid-cols-3 gap-0.5">
                            <div className="col-span-3">
                                <div className="grid grid-cols-2 gap-0.5">
                                    <a href="https://github.com/ml-explore/mlx-lm" target="_blank" rel="noopener noreferrer"
                                        className="bg-white border-2 border-neutral-900 rounded py-0.5 px-1 text-center hover:bg-neutral-50 transition-all duration-300"
                                    >
                                        <div className="flex items-center justify-center gap-0.5">
                                            <span className="w-1 h-1 rounded-full bg-emerald-500 shrink-0" />
                                            <span className="text-[10px] font-semibold text-neutral-900 leading-tight">MLX-LM</span>
                                        </div>
                                        <div className="text-[9px] text-neutral-500 leading-tight">Language Model Inference</div>
                                    </a>
                                    <a href="https://github.com/Blaizzy/mlx-vlm" target="_blank" rel="noopener noreferrer"
                                        className="bg-white border-2 border-neutral-900 rounded py-0.5 px-1 text-center hover:bg-neutral-50 transition-all duration-300"
                                    >
                                        <div className="flex items-center justify-center gap-0.5">
                                            <span className="w-1 h-1 rounded-full bg-emerald-500 shrink-0" />
                                            <span className="text-[10px] font-semibold text-neutral-900 leading-tight">MLX-VLM</span>
                                        </div>
                                        <div className="text-[9px] text-neutral-500 leading-tight">Vision-Language Model Inference</div>
                                    </a>
                                </div>
                            </div>
                            <div className="col-span-3">
                                <a href="https://github.com/ml-explore/mlx" target="_blank" rel="noopener noreferrer"
                                    className="block bg-white border-2 border-neutral-900 rounded py-0.5 px-1 text-center hover:bg-neutral-50 transition-all duration-300"
                                >
                                    <div className="flex items-center justify-center gap-0.5">
                                        <span className="w-1 h-1 rounded-full bg-emerald-500 shrink-0" />
                                        <span className="text-[10px] font-semibold text-neutral-900 leading-tight">MLX</span>
                                    </div>
                                    <div className="text-[9px] text-neutral-500 leading-tight">Apple Silicon ML Framework</div>
                                </a>
                            </div>
                            <div className="col-span-3">
                                <div className="bg-neutral-100 border border-dashed border-neutral-200 rounded py-0.5 px-1 text-center">
                                    <div className="flex items-center justify-center gap-0.5">
                                        <span className="w-1 h-1 rounded-full bg-neutral-300 shrink-0" />
                                        <span className="text-[10px] font-semibold text-neutral-400 leading-tight">Metal</span>
                                    </div>
                                    <div className="text-[9px] text-neutral-300 leading-tight">Apple GPU Hardware Acceleration</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}