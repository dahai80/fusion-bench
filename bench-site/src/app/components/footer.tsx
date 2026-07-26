import Link from "next/link";

export default function Footer() {
    return (
        <footer className="border-t border-neutral-200 bg-neutral-50">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
                    <div className="flex items-center gap-2 text-sm text-neutral-500">
                        <svg width="20" height="20" viewBox="0 0 28 28" fill="none">
                            <rect width="28" height="28" rx="6" fill="#171717" />
                            <path d="M7 19L14 9L21 19" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                        <span>fusion-mlx Community Benchmarks</span>
                    </div>
                    <div className="flex items-center gap-6 text-sm text-neutral-400">
                        <Link href="/get-started" className="hover:text-neutral-600 transition-colors">Get Started</Link>
                        <a href="https://github.com/goatwang/fusion-mlx" target="_blank" rel="noopener noreferrer" className="hover:text-neutral-600 transition-colors">GitHub</a>
                    </div>
                </div>
            </div>
        </footer>
    );
}
