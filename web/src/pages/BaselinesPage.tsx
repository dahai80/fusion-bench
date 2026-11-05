import {
    ConfirmDialog,
    DataTable,
    type DataTableColumn,
    ErrorState,
    SkeletonLines,
} from "@fusion/web-ui";
import { useCallback, useEffect, useState } from "react";
import {
    type Baseline,
    type BaselineDiff,
    type BaselineInput,
    createBaseline,
    deleteBaseline,
    diffBaseline,
    fetchBaselines,
    fetchModels,
    seedBaselines,
} from "../api";
import { useT } from "../i18n";

// #39: named baselines (REST /api/v1/baselines) — list, create, seed,
// delete, and diff current metrics against a baseline.
export function BaselinesPage() {
    const t = useT();
    const [baselines, setBaselines] = useState<Baseline[] | null>(null);
    const [models, setModels] = useState<string[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [pendingDelete, setPendingDelete] = useState<string>("");
    const [form, setForm] = useState<BaselineInput>({
        name: "",
        model: "",
        executor_key: "speed",
        level: "L1",
    });
    const [submitting, setSubmitting] = useState(false);
    // diff panel
    const [diffTarget, setDiffTarget] = useState<Baseline | null>(null);
    const [diffMetrics, setDiffMetrics] = useState("{}");
    const [diff, setDiff] = useState<BaselineDiff | null>(null);

    const load = useCallback(async () => {
        try {
            setBaselines(await fetchBaselines());
            setError(null);
        } catch (e) {
            console.error("[bench-web] baselines load fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
    }, []);

    useEffect(() => {
        load();
        fetchModels()
            .then((ids) => {
                setModels(ids);
                setForm((f) => ({ ...f, model: f.model || ids[0] || "" }));
            })
            .catch((e) => console.error("[bench-web] models load fail:", e));
    }, [load]);

    const onCreate = async () => {
        if (!form.name.trim() || !form.model.trim()) return;
        setSubmitting(true);
        try {
            await createBaseline({ ...form, name: form.name.trim() });
            setForm((f) => ({ ...f, name: "" }));
            setError(null);
            load();
        } catch (e) {
            console.error("[bench-web] baseline create fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
        setSubmitting(false);
    };

    const onSeed = async () => {
        setSubmitting(true);
        try {
            await seedBaselines();
            setError(null);
            load();
        } catch (e) {
            console.error("[bench-web] baseline seed fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
        setSubmitting(false);
    };

    const onDelete = async () => {
        try {
            await deleteBaseline(pendingDelete);
            setError(null);
        } catch (e) {
            console.error("[bench-web] baseline delete fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
        setPendingDelete("");
        load();
    };

    const onDiff = async () => {
        if (!diffTarget) return;
        let metrics: Record<string, number>;
        try {
            metrics = JSON.parse(diffMetrics) as Record<string, number>;
        } catch {
            setError(t("指标需为合法 JSON", "Metrics must be valid JSON"));
            return;
        }
        try {
            const d = await diffBaseline(diffTarget.name, {
                model: diffTarget.model,
                executor_key: diffTarget.executor_key,
                level: diffTarget.level,
                current_metrics: metrics,
            });
            setDiff(d);
            setError(null);
        } catch (e) {
            console.error("[bench-web] baseline diff fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
    };

    if (error && !baselines) {
        return <ErrorState message={error} retryLabel={t("重试", "Retry")} />;
    }
    if (!baselines) {
        return <SkeletonLines rows={6} />;
    }

    const columns: DataTableColumn<Baseline>[] = [
        { key: "name", header: t("名称", "Name") },
        { key: "model", header: t("模型", "Model") },
        { key: "executor_key", header: t("执行器", "Executor") },
        { key: "level", header: t("层级", "Level") },
        {
            key: "metrics",
            header: t("指标", "Metrics"),
            render: (r) => (
                <span className="font-mono text-[10px] text-text-secondary">
                    {Object.keys(r.metrics ?? {}).join(", ") || "-"}
                </span>
            ),
        },
        { key: "created_at", header: t("创建时间", "Created") },
        {
            key: "actions",
            header: t("操作", "Actions"),
            render: (r) => (
                <div className="flex gap-1">
                    <button
                        type="button"
                        onClick={() => {
                            setDiffTarget(r);
                            setDiff(null);
                        }}
                        className="rounded-md border border-border px-2 py-1 text-xs text-text-secondary hover:bg-bg-muted"
                    >
                        {t("对比", "Diff")}
                    </button>
                    <button
                        type="button"
                        onClick={() => setPendingDelete(r.name)}
                        className="rounded-md border border-error/50 px-2 py-1 text-xs text-error hover:bg-error/10"
                    >
                        {t("删除", "Delete")}
                    </button>
                </div>
            ),
        },
    ];

    const diffRows = diff
        ? Object.entries(diff.diffs).map(([metric, d]) => ({ metric, ...d }))
        : [];
    const diffColumns: DataTableColumn<(typeof diffRows)[number]>[] = [
        { key: "metric", header: t("指标", "Metric") },
        {
            key: "baseline",
            header: t("基线", "Baseline"),
            align: "right",
            render: (r) => (r.baseline === null ? "-" : r.baseline.toFixed(4)),
        },
        {
            key: "current",
            header: t("当前", "Current"),
            align: "right",
            render: (r) => (r.current === null ? "-" : r.current.toFixed(4)),
        },
        {
            key: "delta_pct",
            header: t("变化 %", "Delta %"),
            align: "right",
            render: (r) =>
                r.delta_pct === null
                    ? "-"
                    : `${r.delta_pct > 0 ? "+" : ""}${r.delta_pct}%`,
        },
        {
            key: "direction",
            header: t("方向", "Direction"),
            render: (r) => r.direction,
        },
    ];

    const fieldCls =
        "rounded-md border border-border bg-bg px-3 py-2 text-sm text-text-primary";

    return (
        <div className="mx-auto max-w-4xl px-4">
            <div className="mb-3 flex items-center justify-between">
                <h1 className="text-base text-text-primary">
                    {t("基线管理", "Baselines")}
                </h1>
                <button
                    type="button"
                    disabled={submitting}
                    onClick={onSeed}
                    className="rounded-md border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-muted disabled:opacity-40"
                >
                    {t("播种默认基线", "Seed defaults")}
                </button>
            </div>
            <div className="mb-4 rounded-card border border-border bg-bg-elevated p-3">
                <div className="mb-2 text-xs text-text-secondary">
                    {t("新建基线", "New baseline")}
                </div>
                <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                    <input
                        value={form.name}
                        onChange={(e) =>
                            setForm((f) => ({ ...f, name: e.target.value }))
                        }
                        placeholder={t("名称", "name")}
                        className={fieldCls}
                    />
                    <select
                        value={form.model}
                        onChange={(e) =>
                            setForm((f) => ({ ...f, model: e.target.value }))
                        }
                        className={fieldCls}
                    >
                        {models.length === 0 ? (
                            <option value="">
                                {t("模型加载中…", "loading models…")}
                            </option>
                        ) : (
                            models.map((m) => (
                                <option key={m} value={m}>
                                    {m}
                                </option>
                            ))
                        )}
                    </select>
                    <select
                        value={form.executor_key}
                        onChange={(e) =>
                            setForm((f) => ({
                                ...f,
                                executor_key: e.target.value,
                            }))
                        }
                        className={fieldCls}
                    >
                        <option value="speed">speed</option>
                        <option value="accuracy">accuracy</option>
                        <option value="session_slo">session_slo</option>
                    </select>
                    <select
                        value={form.level}
                        onChange={(e) =>
                            setForm((f) => ({ ...f, level: e.target.value }))
                        }
                        className={fieldCls}
                    >
                        <option value="L1">L1</option>
                        <option value="L2">L2</option>
                        <option value="L3">L3</option>
                        <option value="L4">L4</option>
                    </select>
                </div>
                <button
                    type="button"
                    disabled={submitting || !form.name.trim() || !form.model}
                    onClick={onCreate}
                    className="mt-2 rounded-md bg-brand px-4 py-2 text-sm text-white disabled:cursor-not-allowed disabled:opacity-40"
                >
                    {submitting
                        ? t("提交中…", "Submitting…")
                        : t("创建基线", "Create baseline")}
                </button>
            </div>
            {error ? (
                <div className="mb-2 rounded-md border border-error/40 bg-error/10 px-3 py-2 text-xs text-error">
                    {error}
                </div>
            ) : null}
            <DataTable
                columns={columns}
                rows={baselines}
                rowKey={(r) => r.baseline_id}
                pageSize={20}
                emptyState={
                    <div className="py-8 text-center text-xs text-text-muted">
                        {t(
                            "暂无基线 — 创建或点击右上角播种默认基线。",
                            "No baselines yet — create one or seed defaults above.",
                        )}
                    </div>
                }
            />
            {diffTarget ? (
                <div className="mt-4 rounded-card border border-border bg-bg-elevated p-3">
                    <div className="mb-2 flex items-center justify-between">
                        <span className="text-xs text-text-secondary">
                            {t("基线对比", "Baseline diff")} · {diffTarget.name}
                        </span>
                        <button
                            type="button"
                            onClick={() => setDiffTarget(null)}
                            className="text-xs text-text-muted hover:text-text-primary"
                        >
                            ✕
                        </button>
                    </div>
                    <textarea
                        value={diffMetrics}
                        onChange={(e) => setDiffMetrics(e.target.value)}
                        rows={3}
                        className="mb-2 w-full rounded-md border border-border bg-bg p-2 font-mono text-xs text-text-primary"
                        placeholder='{"tok_s": 80.5}'
                        aria-label={t("当前指标 JSON", "current metrics JSON")}
                    />
                    <button
                        type="button"
                        onClick={onDiff}
                        className="rounded-md bg-brand px-4 py-2 text-sm text-white"
                    >
                        {t("运行对比", "Run diff")}
                    </button>
                    {diff ? (
                        diff.baseline_found ? (
                            <div className="mt-3">
                                <DataTable
                                    columns={diffColumns}
                                    rows={diffRows}
                                    rowKey={(r) => r.metric}
                                    pageSize={20}
                                />
                            </div>
                        ) : (
                            <div className="mt-3 text-xs text-text-muted">
                                {t(
                                    "未找到匹配的基线记录（模型/执行器/层级需一致）。",
                                    "No matching baseline record (model/executor/level must match).",
                                )}
                            </div>
                        )
                    ) : null}
                </div>
            ) : null}
            <ConfirmDialog
                open={pendingDelete !== ""}
                danger
                title={`${t("删除", "Delete")} ${pendingDelete}?`}
                confirmName={pendingDelete}
                description={t(
                    "该基线将被删除，且无法恢复。",
                    "The baseline will be deleted and cannot be recovered.",
                )}
                confirmLabel={t("确认", "Confirm")}
                cancelLabel={t("取消", "Cancel")}
                onConfirm={onDelete}
                onCancel={() => setPendingDelete("")}
            />
        </div>
    );
}
