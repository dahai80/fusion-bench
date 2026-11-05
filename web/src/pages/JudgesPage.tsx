import {
    ConfirmDialog,
    DataTable,
    type DataTableColumn,
    ErrorState,
    SkeletonLines,
} from "@fusion/web-ui";
import { useCallback, useEffect, useState } from "react";
import {
    type Judge,
    type JudgeInput,
    createJudge,
    deleteJudge,
    fetchJudges,
    fetchModels,
} from "../api";
import { useT } from "../i18n";

// #39: LLM-as-judge config CRUD (REST /api/v1/judges). SxS pairwise
// judging stays library-level (judge/sxs_judge.py) — no REST surface yet.
export function JudgesPage() {
    const t = useT();
    const [judges, setJudges] = useState<Judge[] | null>(null);
    const [models, setModels] = useState<string[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [pendingDelete, setPendingDelete] = useState<string>("");
    const [form, setForm] = useState<JudgeInput>({
        name: "",
        model: "",
        judge_type: "hybrid",
        weight: 0.5,
        temperature: 0.3,
    });
    const [submitting, setSubmitting] = useState(false);

    const load = useCallback(async () => {
        try {
            setJudges(await fetchJudges());
            setError(null);
        } catch (e) {
            console.error("[bench-web] judges load fail:", e);
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
            await createJudge({ ...form, name: form.name.trim() });
            setForm((f) => ({ ...f, name: "" }));
            setError(null);
            load();
        } catch (e) {
            console.error("[bench-web] judge create fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
        setSubmitting(false);
    };

    const onDelete = async () => {
        try {
            await deleteJudge(pendingDelete);
            setError(null);
        } catch (e) {
            console.error("[bench-web] judge delete fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
        setPendingDelete("");
        load();
    };

    if (error && !judges) {
        return <ErrorState message={error} retryLabel={t("重试", "Retry")} />;
    }
    if (!judges) {
        return <SkeletonLines rows={6} />;
    }

    const columns: DataTableColumn<Judge>[] = [
        { key: "name", header: t("名称", "Name") },
        { key: "model", header: t("模型", "Model") },
        { key: "judge_type", header: t("类型", "Type") },
        {
            key: "weight",
            header: t("权重", "Weight"),
            align: "right",
            render: (r) => r.weight.toFixed(2),
        },
        {
            key: "temperature",
            header: t("温度", "Temp"),
            align: "right",
            render: (r) => r.temperature.toFixed(2),
        },
        { key: "created_at", header: t("创建时间", "Created") },
        {
            key: "actions",
            header: t("操作", "Actions"),
            render: (r) => (
                <button
                    type="button"
                    onClick={() => setPendingDelete(r.name)}
                    className="rounded-md border border-error/50 px-2 py-1 text-xs text-error hover:bg-error/10"
                >
                    {t("删除", "Delete")}
                </button>
            ),
        },
    ];

    const fieldCls =
        "rounded-md border border-border bg-bg px-3 py-2 text-sm text-text-primary";

    return (
        <div className="mx-auto max-w-4xl px-4">
            <h1 className="mb-3 text-base text-text-primary">
                {t("评测裁判", "Judges")}
            </h1>
            <div className="mb-4 rounded-card border border-border bg-bg-elevated p-3">
                <div className="mb-2 text-xs text-text-secondary">
                    {t("新建裁判配置", "New judge config")}
                </div>
                <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
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
                        value={form.judge_type}
                        onChange={(e) =>
                            setForm((f) => ({
                                ...f,
                                judge_type: e.target.value,
                            }))
                        }
                        className={fieldCls}
                    >
                        <option value="hybrid">hybrid</option>
                        <option value="llm">llm</option>
                        <option value="rubric">rubric</option>
                    </select>
                    <input
                        type="number"
                        step="0.1"
                        min="0"
                        max="1"
                        value={form.weight}
                        onChange={(e) =>
                            setForm((f) => ({
                                ...f,
                                weight: Number(e.target.value),
                            }))
                        }
                        className={fieldCls}
                        aria-label={t("权重", "weight")}
                    />
                    <input
                        type="number"
                        step="0.1"
                        min="0"
                        max="2"
                        value={form.temperature}
                        onChange={(e) =>
                            setForm((f) => ({
                                ...f,
                                temperature: Number(e.target.value),
                            }))
                        }
                        className={fieldCls}
                        aria-label={t("温度", "temperature")}
                    />
                </div>
                <button
                    type="button"
                    disabled={submitting || !form.name.trim() || !form.model}
                    onClick={onCreate}
                    className="mt-2 rounded-md bg-brand px-4 py-2 text-sm text-white disabled:cursor-not-allowed disabled:opacity-40"
                >
                    {submitting
                        ? t("提交中…", "Submitting…")
                        : t("创建裁判", "Create judge")}
                </button>
            </div>
            {error ? (
                <div className="mb-2 rounded-md border border-error/40 bg-error/10 px-3 py-2 text-xs text-error">
                    {error}
                </div>
            ) : null}
            <DataTable
                columns={columns}
                rows={judges}
                rowKey={(r) => r.name}
                pageSize={20}
                emptyState={
                    <div className="py-8 text-center text-xs text-text-muted">
                        {t(
                            "暂无裁判配置 — 在上方创建。",
                            "No judges yet — create one above.",
                        )}
                    </div>
                }
            />
            <ConfirmDialog
                open={pendingDelete !== ""}
                danger
                title={`${t("删除", "Delete")} ${pendingDelete}?`}
                confirmName={pendingDelete}
                description={t(
                    "该裁判配置将被删除，且无法恢复。",
                    "The judge config will be deleted and cannot be recovered.",
                )}
                confirmLabel={t("确认", "Confirm")}
                cancelLabel={t("取消", "Cancel")}
                onConfirm={onDelete}
                onCancel={() => setPendingDelete("")}
            />
        </div>
    );
}
