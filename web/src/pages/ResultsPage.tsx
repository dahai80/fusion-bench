import {
    ErrorState,
    MetricChart,
    type MetricPoint,
    MetricTile,
    SkeletonLines,
} from "@fusion/web-ui";
import { useCallback, useEffect, useState } from "react";
import { type TrendPoint, fetchTrend } from "../api";

// issue #23: result charts — metric trend from /api/v1/results/trend.
export function ResultsPage() {
    const [trend, setTrend] = useState<TrendPoint[] | null>(null);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        try {
            setTrend(await fetchTrend(100));
            setError(null);
        } catch (e) {
            console.error("[bench-web] trend load fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
    }, []);

    useEffect(() => {
        load();
        const t = setInterval(load, 15_000);
        return () => clearInterval(t);
    }, [load]);

    if (error && !trend) {
        return <ErrorState message={error} retryLabel="Retry" />;
    }
    if (!trend) {
        return <SkeletonLines rows={4} />;
    }

    const points: MetricPoint[] = trend.map((p) => ({
        t: new Date(p.timestamp).getTime(),
        v: p.metric_value,
    }));
    const latest = trend.length > 0 ? trend[trend.length - 1] : null;
    const models = new Set(trend.map((p) => p.model)).size;
    const avg =
        trend.length > 0
            ? trend.reduce((s, p) => s + p.metric_value, 0) / trend.length
            : 0;

    return (
        <div className="mx-auto max-w-4xl px-4">
            <div className="mb-3 flex items-center justify-between">
                <h1 className="text-base text-text-primary">Results</h1>
                <span className="text-xs text-text-muted">
                    {trend.length} runs · 15s poll
                </span>
            </div>
            <div className="flex flex-col gap-3">
                <div className="grid grid-cols-3 gap-2">
                    <MetricTile
                        label="Latest metric"
                        value={latest ? latest.metric_value.toFixed(3) : "-"}
                    />
                    <MetricTile label="Average metric" value={avg.toFixed(3)} />
                    <MetricTile label="Models" value={models} />
                </div>
                <MetricChart
                    series={[
                        {
                            label: "metric_value trend",
                            points,
                        },
                    ]}
                />
            </div>
        </div>
    );
}
