import {
    ConfirmDialog,
    DataTable,
    type DataTableColumn,
    ErrorState,
    SkeletonLines,
    StatusBadge,
    type StatusKind,
    TaskProgress,
} from "@fusion/web-ui";
import { useCallback, useEffect, useState } from "react";
import {
    type SubmitInput,
    type TaskDetail,
    type TaskSummary,
    cancelTask,
    fetchTask,
    fetchTasks,
    retryTask,
    submitTask,
} from "../api";

// issue #23: bench task submit + list + run progress. Cancel/retry are
// destructive ops behind a danger confirm (spec S5).
function statusToKind(status: string): StatusKind {
    switch (status) {
        case "completed":
            return "success";
        case "running":
        case "pending":
            return "running";
        case "failed":
            return "error";
        case "cancelled":
            return "warning";
        default:
            return "offline";
    }
}

type PendingOp =
    | { kind: "cancel"; taskId: string }
    | { kind: "retry"; taskId: string };

export function TasksPage() {
    const [tasks, setTasks] = useState<TaskSummary[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [pending, setPending] = useState<PendingOp | null>(null);
    const [detail, setDetail] = useState<TaskDetail | null>(null);
    const [selected, setSelected] = useState<string>("");
    // submit form state
    const [model, setModel] = useState("");
    const [executorKey, setExecutorKey] = useState("speed");
    const [level, setLevel] = useState("L1");
    const [suite, setSuite] = useState("");
    const [submitting, setSubmitting] = useState(false);

    const load = useCallback(async () => {
        try {
            setTasks(await fetchTasks());
            setError(null);
        } catch (e) {
            console.error("[bench-web] tasks load fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
    }, []);

    useEffect(() => {
        load();
        const t = setInterval(load, 5000);
        return () => clearInterval(t);
    }, [load]);

    // selected task detail poll (progress while running)
    useEffect(() => {
        if (!selected) {
            setDetail(null);
            return;
        }
        let stop = false;
        const loadDetail = async () => {
            try {
                const d = await fetchTask(selected);
                if (!stop) setDetail(d);
            } catch (e) {
                console.error("[bench-web] task detail load fail:", e);
            }
        };
        loadDetail();
        const t = setInterval(loadDetail, 2000);
        return () => {
            stop = true;
            clearInterval(t);
        };
    }, [selected]);

    const onSubmit = async () => {
        if (!model.trim()) return;
        setSubmitting(true);
        try {
            const input: SubmitInput = {
                model: model.trim(),
                executor_key: executorKey,
                level,
            };
            if (suite) input.suite = suite;
            const created = await submitTask(input);
            setSelected(created.task_id);
            setError(null);
            load();
        } catch (e) {
            console.error("[bench-web] submit fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
        setSubmitting(false);
    };

    const runOp = async () => {
        if (!pending) return;
        try {
            if (pending.kind === "cancel") {
                await cancelTask(pending.taskId);
            } else {
                const created = await retryTask(pending.taskId);
                setSelected(created.task_id);
            }
            setError(null);
        } catch (e) {
            console.error("[bench-web] op fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
        setPending(null);
        load();
    };

    if (error && !tasks) {
        return <ErrorState message={error} retryLabel="Retry" />;
    }
    if (!tasks) {
        return <SkeletonLines rows={6} />;
    }

    const columns: DataTableColumn<TaskSummary>[] = [
        {
            key: "task_id",
            header: "Task",
            render: (r) => (
                <button
                    type="button"
                    onClick={() => setSelected(r.task_id)}
                    className={`font-mono text-xs ${
                        selected === r.task_id
                            ? "text-brand"
                            : "text-text-primary underline-offset-2 hover:underline"
                    }`}
                >
                    {r.task_id}
                </button>
            ),
        },
        {
            key: "status",
            header: "Status",
            render: (r) => (
                <StatusBadge status={statusToKind(r.status)} label={r.status} />
            ),
        },
        { key: "model", header: "Model", sortable: true },
        { key: "executor_key", header: "Executor" },
        { key: "level", header: "Level" },
        {
            key: "actions",
            header: "Actions",
            render: (r) => (
                <div className="flex gap-1">
                    {r.status === "pending" || r.status === "running" ? (
                        <ActionBtn
                            label="Cancel"
                            danger
                            onClick={() =>
                                setPending({
                                    kind: "cancel",
                                    taskId: r.task_id,
                                })
                            }
                        />
                    ) : null}
                    {r.status === "failed" || r.status === "cancelled" ? (
                        <ActionBtn
                            label="Retry"
                            onClick={() =>
                                setPending({ kind: "retry", taskId: r.task_id })
                            }
                        />
                    ) : null}
                </div>
            ),
        },
    ];

    return (
        <div className="mx-auto max-w-4xl px-4">
            <h1 className="mb-3 text-base text-text-primary">Tasks</h1>
            <div className="mb-4 rounded-card border border-border bg-bg-elevated p-3">
                <div className="mb-2 text-xs text-text-secondary">
                    New benchmark task
                </div>
                <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                    <input
                        value={model}
                        onChange={(e) => setModel(e.target.value)}
                        placeholder="model (e.g. qwen3.5-9b)"
                        className="rounded-md border border-border bg-bg px-3 py-2 font-mono text-sm text-text-primary outline-none focus:border-brand"
                    />
                    <select
                        value={executorKey}
                        onChange={(e) => setExecutorKey(e.target.value)}
                        className="rounded-md border border-border bg-bg px-3 py-2 text-sm text-text-primary"
                    >
                        <option value="speed">speed</option>
                        <option value="accuracy">accuracy</option>
                        <option value="session_slo">session_slo</option>
                    </select>
                    <select
                        value={level}
                        onChange={(e) => setLevel(e.target.value)}
                        className="rounded-md border border-border bg-bg px-3 py-2 text-sm text-text-primary"
                    >
                        <option value="L1">L1</option>
                        <option value="L2">L2</option>
                        <option value="L3">L3</option>
                        <option value="L4">L4</option>
                    </select>
                    <select
                        value={suite}
                        onChange={(e) => setSuite(e.target.value)}
                        className="rounded-md border border-border bg-bg px-3 py-2 text-sm text-text-primary"
                    >
                        <option value="">suite: none</option>
                        <option value="quick">quick</option>
                        <option value="standard">standard</option>
                        <option value="full">full</option>
                        <option value="long-session">long-session</option>
                    </select>
                </div>
                <button
                    type="button"
                    disabled={submitting || !model.trim()}
                    onClick={onSubmit}
                    className="mt-2 rounded-md bg-brand px-4 py-2 text-sm text-white disabled:cursor-not-allowed disabled:opacity-40"
                >
                    {submitting ? "Submitting…" : "Submit task"}
                </button>
            </div>
            {error ? (
                <div className="mb-2 rounded-md border border-error/40 bg-error/10 px-3 py-2 text-xs text-error">
                    {error}
                </div>
            ) : null}
            <DataTable
                columns={columns}
                rows={tasks}
                rowKey={(r) => r.task_id}
                pageSize={20}
                emptyState={
                    <div className="py-8 text-center text-xs text-text-muted">
                        No tasks yet — submit one above.
                    </div>
                }
            />
            {detail ? (
                <div className="mt-4 rounded-card border border-border bg-bg-elevated p-3">
                    <div className="mb-2 flex items-center justify-between">
                        <span className="font-mono text-xs text-text-primary">
                            {detail.task_id}
                        </span>
                        <StatusBadge
                            status={statusToKind(detail.status)}
                            label={detail.status}
                        />
                    </div>
                    <TaskProgress
                        stage={`${detail.model} · ${detail.executor_key} · ${detail.level}`}
                        current={Math.round(detail.progress * 100)}
                        total={100}
                    />
                    {detail.error ? (
                        <div className="mt-2 rounded-md border border-error/40 bg-error/10 px-3 py-2 text-xs text-error">
                            {detail.error}
                        </div>
                    ) : null}
                    {detail.result ? (
                        <pre className="mt-2 max-h-40 overflow-auto rounded-md bg-bg-muted p-2 font-mono text-[10px] text-text-secondary">
                            {JSON.stringify(detail.result, null, 2)}
                        </pre>
                    ) : null}
                </div>
            ) : null}
            <ConfirmDialog
                open={pending !== null}
                danger
                title={pending ? `${pending.kind} ${pending.taskId}?` : ""}
                description={
                    pending?.kind === "cancel"
                        ? "The running benchmark task is cancelled and cannot be resumed."
                        : "A new task is created re-running the same request."
                }
                confirmLabel="Confirm"
                cancelLabel="Cancel"
                onConfirm={runOp}
                onCancel={() => setPending(null)}
            />
        </div>
    );
}

function ActionBtn({
    label,
    onClick,
    danger,
}: { label: string; onClick: () => void; danger?: boolean }) {
    return (
        <button
            type="button"
            onClick={onClick}
            className={`rounded-md border px-2 py-1 text-xs ${
                danger
                    ? "border-error/50 text-error hover:bg-error/10"
                    : "border-border text-text-secondary hover:bg-bg-muted"
            }`}
        >
            {label}
        </button>
    );
}
