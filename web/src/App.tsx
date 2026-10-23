import { useEffect, useState } from "react";
import { ComparePage } from "./pages/ComparePage";
import { ResultsPage } from "./pages/ResultsPage";
import { TasksPage } from "./pages/TasksPage";
import { embeddedParam, isEmbedded } from "./sdk";

// Hash router (no router dep). Standalone shows a bottom tab bar; embedded
// (?embedded=1 or iframe) the shell owns the chrome.
type Route = "tasks" | "results" | "compare";

const ROUTES: ReadonlySet<string> = new Set<Route>([
    "tasks",
    "results",
    "compare",
]);

function parseHash(): Route {
    const h = window.location.hash.replace(/^#\/?/, "");
    if (ROUTES.has(h)) return h as Route;
    return "tasks";
}

export function App() {
    const [route, setRoute] = useState<Route>(parseHash());

    useEffect(() => {
        const onHash = () => setRoute(parseHash());
        window.addEventListener("hashchange", onHash);
        return () => window.removeEventListener("hashchange", onHash);
    }, []);

    const embedded = embeddedParam() || isEmbedded();

    return (
        <div className={embedded ? "h-full" : "flex h-full flex-col"}>
            {embedded && <EmbeddedTabs route={route} onChange={setRoute} />}
            <main className={`min-h-0 flex-1 ${embedded ? "" : "pb-16 pt-4"}`}>
                {route === "tasks" && <TasksPage />}
                {route === "results" && <ResultsPage />}
                {route === "compare" && <ComparePage />}
            </main>
            {!embedded && <BottomNav route={route} onChange={setRoute} />}
        </div>
    );
}

const NAV_ITEMS: Array<{ id: Route; label: string }> = [
    { id: "tasks", label: "Tasks" },
    { id: "results", label: "Results" },
    { id: "compare", label: "Compare" },
];

function EmbeddedTabs({
    route,
    onChange,
}: { route: Route; onChange: (r: Route) => void }) {
    return (
        <nav className="flex shrink-0 border-b border-border bg-bg-elevated">
            {NAV_ITEMS.map((it) => (
                <button
                    key={it.id}
                    type="button"
                    onClick={() => onChange(it.id)}
                    className={`flex-1 py-2 text-center text-xs uppercase tracking-wide ${
                        route === it.id
                            ? "border-b-2 border-brand text-brand"
                            : "text-text-secondary"
                    }`}
                >
                    {it.label}
                </button>
            ))}
        </nav>
    );
}

function BottomNav({
    route,
    onChange,
}: { route: Route; onChange: (r: Route) => void }) {
    return (
        <nav className="fixed inset-x-0 bottom-0 z-10 flex border-t border-border bg-bg-elevated">
            {NAV_ITEMS.map((it) => (
                <button
                    key={it.id}
                    type="button"
                    onClick={() => onChange(it.id)}
                    className={`flex-1 py-3 text-center text-sm ${
                        route === it.id ? "text-brand" : "text-text-secondary"
                    }`}
                >
                    {it.label}
                </button>
            ))}
        </nav>
    );
}
