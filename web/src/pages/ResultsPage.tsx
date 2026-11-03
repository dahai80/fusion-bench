import {
    ErrorState,
    MetricChart,
    type MetricPoint,
    MetricTile,
    SkeletonLines,
} from "@fusion/web-ui";
import { useCallback, useEffect, useState } from "react";
import { type TrendPoint, fetchTrend } from "../api";
import { useT } from "../i18n";

// issue #23: result charts — metric trend from /api/v1/results/trend.
export function ResultsPage() {
    const t = useT();
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
        return <ErrorState message={error} retryLabel={t("重试", "Retry")} />;
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
                <h1 className="text-base text-text-primary">
                    {t("评测结果", "Results")}
                </h1>
                <span className="text-xs text-text-muted">
                    {t(
                        `${trend.length} 次运行 · 15s 刷新`,
                        `${trend.length} runs · 15s poll`,
                    )}
                </span>
            </div>
            <div className="flex flex-col gap-3">
                <div className="grid grid-cols-3 gap-2">
                    <MetricTile
                        label={t("最新指标", "Latest metric")}
                        value={latest ? latest.metric_value.toFixed(3) : "-"}
                    />
                    <MetricTile
                        label={t("平均指标", "Average metric")}
                        value={avg.toFixed(3)}
                    />
                    <MetricTile label={t("模型数", "Models")} value={models} />
                </div>
                <MetricChart
                    series={[
                        {
                            label: t("指标趋势", "metric_value trend"),
                            points,
                        },
                    ]}
                />
            </div>
        </div>
    );
}
