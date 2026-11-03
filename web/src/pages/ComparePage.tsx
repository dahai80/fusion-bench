import {
    DataTable,
    type DataTableColumn,
    ErrorState,
    SkeletonLines,
} from "@fusion/web-ui";
import { useCallback, useEffect, useState } from "react";
import {
    type CompareRow,
    type TaskSummary,
    fetchCompare,
    fetchTasks,
} from "../api";
import { useT } from "../i18n";

// issue #23: historical comparison — pick 2+ completed tasks, POST
// /api/v1/results/compare, render metric rows in a DataTable.
interface CompareRowView {
    task_id: string;
    metric_name: string;
    metric_value: number;
    pass_rate: number;
    num_cases: number;
}

function toView(row: CompareRow): CompareRowView {
    const r = (row.result ?? {}) as Record<string, unknown>;
    return {
        task_id: row.task_id,
        metric_name: String(r.metric_name ?? ""),
        metric_value: Number(r.metric_value ?? 0),
        pass_rate: Number(r.pass_rate ?? 0),
        num_cases: Number(r.num_cases ?? 0),
    };
}

export function ComparePage() {
    const t = useT();
    const [tasks, setTasks] = useState<TaskSummary[] | null>(null);
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [rows, setRows] = useState<CompareRowView[] | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        fetchTasks(1, 50)
            .then((list) =>
                setTasks(list.filter((t) => t.status === "completed")),
            )
            .catch((e) => {
                console.error("[bench-web] task list fail:", e);
                setError(e instanceof Error ? e.message : String(e));
            });
    }, []);

    const toggle = (taskId: string) => {
        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(taskId)) {
                next.delete(taskId);
            } else {
                next.add(taskId);
            }
            return next;
        });
    };

    const runCompare = useCallback(async () => {
        if (selected.size < 2) return;
        try {
            const compared = await fetchCompare([...selected]);
            setRows(compared.map(toView));
            setError(null);
        } catch (e) {
            console.error("[bench-web] compare fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
    }, [selected]);

    if (error && !tasks) {
        return <ErrorState message={error} retryLabel={t("重试", "Retry")} />;
    }
    if (!tasks) {
        return <SkeletonLines rows={6} />;
    }

    const columns: DataTableColumn<CompareRowView>[] = [
        {
            key: "task_id",
            header: t("任务", "Task"),
            render: (r) => (
                <span className="font-mono text-xs text-text-primary">
                    {r.task_id}
                </span>
            ),
        },
        { key: "metric_name", header: t("指标", "Metric") },
        {
            key: "metric_value",
            header: t("数值", "Value"),
            sortable: true,
            align: "right",
            render: (r) => (
                <span className="font-mono tabular-nums text-text-primary">
                    {r.metric_value.toFixed(4)}
                </span>
            ),
        },
        {
            key: "pass_rate",
            header: t("通过率", "Pass rate"),
            sortable: true,
            align: "right",
            render: (r) => (
                <span className="font-mono tabular-nums text-text-primary">
                    {(r.pass_rate * 100).toFixed(1)}%
                </span>
            ),
        },
        { key: "num_cases", header: t("用例数", "Cases"), align: "right" },
    ];

    return (
        <div className="mx-auto max-w-4xl px-4">
            <div className="mb-3 flex items-center justify-between">
                <h1 className="text-base text-text-primary">
                    {t("历史对比", "Compare")}
                </h1>
                <button
                    type="button"
                    disabled={selected.size < 2}
                    onClick={runCompare}
                    className="rounded-md bg-brand px-4 py-2 text-sm text-white disabled:cursor-not-allowed disabled:opacity-40"
                >
                    {t(
                        `对比 ${selected.size} 个任务`,
                        `Compare ${selected.size} tasks`,
                    )}
                </button>
            </div>
            {error ? (
                <div className="mb-2 rounded-md border border-error/40 bg-error/10 px-3 py-2 text-xs text-error">
                    {error}
                </div>
            ) : null}
            <div className="mb-4 rounded-card border border-border bg-bg-elevated p-3">
                <div className="mb-2 text-xs text-text-secondary">
                    {t(
                        "选择至少 2 个已完成的任务",
                        "Select at least 2 completed tasks",
                    )}
                </div>
                <div className="flex max-h-32 flex-wrap gap-1 overflow-auto">
                    {tasks.map((t) => (
                        <button
                            key={t.task_id}
                            type="button"
                            onClick={() => toggle(t.task_id)}
                            className={`rounded-md border px-2 py-1 font-mono text-xs ${
                                selected.has(t.task_id)
                                    ? "border-brand bg-brand/10 text-brand"
                                    : "border-border text-text-secondary hover:bg-bg-muted"
                            }`}
                        >
                            {t.task_id}
                        </button>
                    ))}
                </div>
            </div>
            {rows ? (
                <DataTable
                    columns={columns}
                    rows={rows}
                    rowKey={(r) => r.task_id}
                    pageSize={20}
                />
            ) : (
                <div className="py-8 text-center text-xs text-text-muted">
                    {t(
                        "在上方选择 2 个以上任务后点击对比。",
                        "Pick 2+ tasks above, then Compare.",
                    )}
                </div>
            )}
        </div>
    );
}
