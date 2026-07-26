"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
    { href: "/", label: "Home" },
    { href: "/get-started", label: "Get Started" },
    { href: "/performance", label: "Performance" },
    { href: "/benchmarks", label: "Benchmarks" },
    { href: "/compare", label: "Compare" },
];

const EXTERNAL_LINKS = [
    {
        href: "https://github.com/dahai80/fusion-mlx",
        label: "GitHub",
        icon: (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
            </svg>
        ),
    },
    {
        href: "https://github.com/dahai80/fusion-mlx/releases",
        label: "Download",
        icon: (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M8 2v8m0 0l-3-3m3 3l3-3M2 12v1a1 1 0 001 1h10a1 1 0 001-1v-1" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
        ),
    },
];

export default function Navbar() {
    const pathname = usePathname();

    return (
        <nav className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-neutral-200">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="flex items-center justify-between h-16">
                    <Link href="/" className="flex items-center gap-2 font-bold text-xl text-neutral-900">
                        <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <rect width="28" height="28" rx="6" fill="#171717" />
                            <path d="M7 19L14 9L21 19" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                        <span>fusion-mlx</span>
                    </Link>

                    <div className="hidden md:flex items-center gap-1">
                        <div className="flex items-center gap-1 bg-neutral-100 rounded-full p-1">
                            {NAV_ITEMS.map((item) => {
                                const isActive = pathname === item.href ||
                                    (item.href !== "/" && pathname.startsWith(item.href));
                                return (
                                    <Link
                                        key={item.href}
                                        href={item.href}
                                        className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                                            isActive
                                                ? "bg-white text-neutral-900 shadow-sm"
                                                : "text-neutral-500 hover:text-neutral-900"
                                        }`}
                                    >
                                        {item.label}
                                    </Link>
                                );
                            })}
                        </div>
                        <div className="flex items-center gap-1 ml-2">
                            {EXTERNAL_LINKS.map((item) => (
                                <a
                                    key={item.href}
                                    href={item.href}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="flex items-center gap-1.5 px-3 py-2 rounded-full text-sm font-medium text-neutral-500 hover:text-neutral-900 hover:bg-neutral-100 transition-colors"
                                >
                                    {item.icon}
                                    {item.label}
                                </a>
                            ))}
                        </div>
                    </div>

                    <MobileMenu pathname={pathname} />
                </div>
            </div>
        </nav>
    );
}

function MobileMenu({ pathname }: { pathname: string }) {
    return (
        <div className="md:hidden relative group">
            <button className="p-2 text-neutral-600 hover:text-neutral-900">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 12h18M3 6h18M3 18h18" />
                </svg>
            </button>
            <div className="absolute right-0 top-full mt-2 w-56 bg-white rounded-xl shadow-lg border border-neutral-200 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all py-2">
                {NAV_ITEMS.map((item) => {
                    const isActive = pathname === item.href ||
                        (item.href !== "/" && pathname.startsWith(item.href));
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={`block px-4 py-2.5 text-sm ${
                                isActive ? "bg-neutral-50 text-neutral-900 font-medium" : "text-neutral-600 hover:bg-neutral-50"
                            }`}
                        >
                            {item.label}
                        </Link>
                    );
                })}
                <div className="border-t border-neutral-100 my-1" />
                {EXTERNAL_LINKS.map((item) => (
                    <a
                        key={item.href}
                        href={item.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-2 px-4 py-2.5 text-sm text-neutral-600 hover:bg-neutral-50"
                    >
                        {item.icon}
                        {item.label}
                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" className="ml-auto opacity-40">
                            <path d="M3 9L9 3m0 0H5m4 0v4" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                    </a>
                ))}
            </div>
        </div>
    );
}
