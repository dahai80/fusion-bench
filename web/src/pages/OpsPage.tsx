import {
    ConfirmDialog,
    DataTable,
    type DataTableColumn,
    ErrorState,
    SkeletonLines,
    StatusBadge,
    type StatusKind,
} from "@fusion/web-ui";
import { useCallback, useEffect, useState } from "react";
import {
    type Approval,
    type AuditEntry,
    type BackupEntry,
    type Schedule,
    type ScheduleInput,
    createBackup,
    createSchedule,
    decideApproval,
    deleteSchedule,
    fetchApprovals,
    fetchAuditLogs,
    fetchBackups,
    fetchModels,
    fetchSchedules,
    restoreBackup,
    toggleSchedule,
} from "../api";
import { useT } from "../i18n";

// #39: cron schedules (toggle/delete/create) + gate approval workflow
// (pending filter, approve/reject with approver + remark) + backup/
// restore + audit logs.
function approvalKind(status: string): StatusKind {
    switch (status) {
        case "approved":
            return "success";
        case "rejected":
            return "error";
        case "expired":
            return "warning";
        default:
            return "running";
    }
}

function approvalZh(status: string): string {
    switch (status) {
        case "approved":
            return "已通过";
        case "rejected":
            return "已驳回";
        case "expired":
            return "已过期";
        case "pending":
            return "待审批";
        default:
            return status;
    }
}

export function OpsPage() {
    const t = useT();
    const [schedules, setSchedules] = useState<Schedule[] | null>(null);
    const [approvals, setApprovals] = useState<Approval[] | null>(null);
    const [backups, setBackups] = useState<BackupEntry[]>([]);
    const [audit, setAudit] = useState<AuditEntry[]>([]);
    const [pendingRestore, setPendingRestore] = useState<string>("");
    const [backupBusy, setBackupBusy] = useState(false);
    const [pendingOnly, setPendingOnly] = useState(true);
    const [models, setModels] = useState<string[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [pendingDelete, setPendingDelete] = useState<string>("");
    const [pendingDecision, setPendingDecision] = useState<{
        requestId: string;
        decision: "approve" | "reject";
    } | null>(null);
    const [decisionRemark, setDecisionRemark] = useState("");
    const [form, setForm] = useState<ScheduleInput>({
        name: "",
        cron: "0 9 * * *",
        model: "",
        executor_key: "speed",
        level: "L1",
    });
    const [submitting, setSubmitting] = useState(false);

    const load = useCallback(async () => {
        try {
            const [s, a] = await Promise.all([
                fetchSchedules(),
                fetchApprovals(pendingOnly),
            ]);
            setSchedules(s);
            setApprovals(a);
            setError(null);
        } catch (e) {
            console.error("[bench-web] ops load fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
    }, [pendingOnly]);

    const loadSystem = useCallback(async () => {
        // Backup + audit surfaces are best-effort: admin-gated endpoints
        // may 403 for operator tenants — keep the page usable.
        try {
            setBackups(await fetchBackups());
        } catch (e) {
            console.error("[bench-web] backups load fail:", e);
        }
        try {
            setAudit(await fetchAuditLogs(20));
        } catch (e) {
            console.error("[bench-web] audit load fail:", e);
        }
    }, []);

    useEffect(() => {
        load();
        loadSystem();
        fetchModels()
            .then((ids) => {
                setModels(ids);
                setForm((f) => ({ ...f, model: f.model || ids[0] || "" }));
            })
            .catch((e) => console.error("[bench-web] models load fail:", e));
    }, [load, loadSystem]);

    const onBackup = async () => {
        setBackupBusy(true);
        try {
            await createBackup();
            setError(null);
            loadSystem();
        } catch (e) {
            console.error("[bench-web] backup create fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
        setBackupBusy(false);
    };

    const onRestore = async () => {
        try {
            await restoreBackup(pendingRestore);
            setError(null);
        } catch (e) {
            console.error("[bench-web] backup restore fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
        setPendingRestore("");
        loadSystem();
    };

    const onCreate = async () => {
        if (!form.name.trim() || !form.cron.trim() || !form.model) return;
        setSubmitting(true);
        try {
            await createSchedule({ ...form, name: form.name.trim() });
            setForm((f) => ({ ...f, name: "" }));
            setError(null);
            load();
        } catch (e) {
            console.error("[bench-web] schedule create fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
        setSubmitting(false);
    };

    const onToggle = async (scheduleId: string) => {
        try {
            await toggleSchedule(scheduleId);
            setError(null);
        } catch (e) {
            console.error("[bench-web] schedule toggle fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
        load();
    };

    const onDelete = async () => {
        try {
            await deleteSchedule(pendingDelete);
            setError(null);
        } catch (e) {
            console.error("[bench-web] schedule delete fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
        setPendingDelete("");
        load();
    };

    const onDecide = async () => {
        if (!pendingDecision) return;
        try {
            await decideApproval(
                pendingDecision.requestId,
                pendingDecision.decision,
                "shell",
                decisionRemark,
            );
            setError(null);
        } catch (e) {
            console.error("[bench-web] approval decide fail:", e);
            setError(e instanceof Error ? e.message : String(e));
        }
        setPendingDecision(null);
        setDecisionRemark("");
        load();
    };

    if (error && (!schedules || !approvals)) {
        return <ErrorState message={error} retryLabel={t("重试", "Retry")} />;
    }
    if (!schedules || !approvals) {
        return <SkeletonLines rows={6} />;
    }

    const scheduleColumns: DataTableColumn<Schedule>[] = [
        { key: "name", header: t("名称", "Name") },
        {
            key: "cron",
            header: "Cron",
            render: (r) => (
                <span className="font-mono text-xs text-text-primary">
                    {r.cron}
                </span>
            ),
        },
        { key: "model", header: t("模型", "Model") },
        { key: "executor_key", header: t("执行器", "Executor") },
        {
            key: "enabled",
            header: t("状态", "Status"),
            render: (r) =>
                r.enabled ? (
                    <StatusBadge
                        status="success"
                        label={t("已启用", "enabled")}
                    />
                ) : (
                    <StatusBadge
                        status="offline"
                        label={t("已停用", "disabled")}
                    />
                ),
        },
        {
            key: "actions",
            header: t("操作", "Actions"),
            render: (r) => (
                <div className="flex gap-1">
                    <button
                        type="button"
                        onClick={() => onToggle(r.schedule_id)}
                        className="rounded-md border border-border px-2 py-1 text-xs text-text-secondary hover:bg-bg-muted"
                    >
                        {r.enabled ? t("停用", "Disable") : t("启用", "Enable")}
                    </button>
                    <button
                        type="button"
                        onClick={() => setPendingDelete(r.schedule_id)}
                        className="rounded-md border border-error/50 px-2 py-1 text-xs text-error hover:bg-error/10"
                    >
                        {t("删除", "Delete")}
                    </button>
                </div>
            ),
        },
    ];

    const approvalColumns: DataTableColumn<Approval>[] = [
        { key: "gate_name", header: t("质量门", "Gate") },
        {
            key: "metric_name",
            header: t("指标", "Metric"),
            render: (r) => (
                <span className="font-mono text-xs text-text-primary">
                    {r.metric_name} {r.metric_value} / {r.threshold}
                </span>
            ),
        },
        { key: "requester", header: t("发起人", "Requester") },
        {
            key: "status",
            header: t("状态", "Status"),
            render: (r) => (
                <StatusBadge
                    status={approvalKind(r.status)}
                    label={t(approvalZh(r.status), r.status)}
                />
            ),
        },
        ...(pendingOnly
            ? [
                  {
                      key: "actions",
                      header: t("操作", "Actions"),
                      render: (r: Approval) =>
                          r.status === "pending" ? (
                              <div className="flex gap-1">
                                  <button
                                      type="button"
                                      onClick={() =>
                                          setPendingDecision({
                                              requestId: r.request_id,
                                              decision: "approve",
                                          })
                                      }
                                      className="rounded-md border border-border px-2 py-1 text-xs text-text-primary hover:bg-bg-muted"
                                  >
                                      {t("通过", "Approve")}
                                  </button>
                                  <button
                                      type="button"
                                      onClick={() =>
                                          setPendingDecision({
                                              requestId: r.request_id,
                                              decision: "reject",
                                          })
                                      }
                                      className="rounded-md border border-error/50 px-2 py-1 text-xs text-error hover:bg-error/10"
                                  >
                                      {t("驳回", "Reject")}
                                  </button>
                              </div>
                          ) : null,
                  } satisfies DataTableColumn<Approval>,
              ]
            : []),
    ];

    const fieldCls =
        "rounded-md border border-border bg-bg px-3 py-2 text-sm text-text-primary";

    const backupColumns: DataTableColumn<BackupEntry>[] = [
        {
            key: "label",
            header: t("标签", "Label"),
            render: (r) => (
                <span className="font-mono text-xs text-text-primary">
                    {r.label}
                </span>
            ),
        },
        {
            key: "file_count",
            header: t("文件数", "Files"),
            align: "right",
        },
        {
            key: "total_size",
            header: t("大小", "Size"),
            align: "right",
            render: (r) => `${(r.total_size / 1024).toFixed(1)} KiB`,
        },
        {
            key: "actions",
            header: t("操作", "Actions"),
            render: (r) => (
                <button
                    type="button"
                    onClick={() => setPendingRestore(r.label)}
                    className="rounded-md border border-border px-2 py-1 text-xs text-text-secondary hover:bg-bg-muted"
                >
                    {t("恢复", "Restore")}
                </button>
            ),
        },
    ];

    const auditColumns: DataTableColumn<AuditEntry>[] = [
        {
            key: "timestamp",
            header: t("时间", "Time"),
            render: (r) => (
                <span className="font-mono text-xs text-text-secondary">
                    {r.timestamp.slice(0, 19)}
                </span>
            ),
        },
        { key: "actor", header: t("操作者", "Actor") },
        {
            key: "action",
            header: t("动作", "Action"),
            render: (r) => (
                <span className="font-mono text-xs text-text-primary">
                    {r.action}
                </span>
            ),
        },
        { key: "resource_type", header: t("对象类型", "Resource") },
        { key: "resource_id", header: t("对象", "ID") },
    ];

    return (
        <div className="mx-auto max-w-4xl px-4">
            <h1 className="mb-3 text-base text-text-primary">
                {t("调度与审批", "Schedules & Approvals")}
            </h1>

            <div className="mb-4 rounded-card border border-border bg-bg-elevated p-3">
                <div className="mb-2 text-xs text-text-secondary">
                    {t("新建调度", "New schedule")}
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
                    <input
                        value={form.cron}
                        onChange={(e) =>
                            setForm((f) => ({ ...f, cron: e.target.value }))
                        }
                        className={`${fieldCls} font-mono`}
                        aria-label="cron"
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
                        : t("创建调度", "Create schedule")}
                </button>
            </div>

            {error ? (
                <div className="mb-2 rounded-md border border-error/40 bg-error/10 px-3 py-2 text-xs text-error">
                    {error}
                </div>
            ) : null}

            <DataTable
                columns={scheduleColumns}
                rows={schedules}
                rowKey={(r) => r.schedule_id}
                pageSize={20}
                emptyState={
                    <div className="py-8 text-center text-xs text-text-muted">
                        {t(
                            "暂无调度 — 在上方创建。",
                            "No schedules yet — create one above.",
                        )}
                    </div>
                }
            />

            <div className="mt-6 mb-3 flex items-center justify-between">
                <h2 className="text-sm text-text-primary">
                    {t("质量门审批", "Gate approvals")}
                </h2>
                <button
                    type="button"
                    onClick={() => setPendingOnly((v) => !v)}
                    className="rounded-md border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-muted"
                >
                    {pendingOnly
                        ? t("查看全部", "Show all")
                        : t("只看待审批", "Pending only")}
                </button>
            </div>
            <DataTable
                columns={approvalColumns}
                rows={approvals}
                rowKey={(r) => r.request_id}
                pageSize={20}
                emptyState={
                    <div className="py-8 text-center text-xs text-text-muted">
                        {t("暂无审批请求。", "No approval requests.")}
                    </div>
                }
            />

            <div className="mt-6 mb-3 flex items-center justify-between">
                <h2 className="text-sm text-text-primary">
                    {t("备份与恢复", "Backup & Restore")}
                </h2>
                <button
                    type="button"
                    disabled={backupBusy}
                    onClick={onBackup}
                    className="rounded-md border border-border px-3 py-1.5 text-xs text-text-secondary hover:bg-bg-muted disabled:opacity-40"
                >
                    {backupBusy
                        ? t("备份中…", "Backing up…")
                        : t("创建备份", "Create backup")}
                </button>
            </div>
            <DataTable
                columns={backupColumns}
                rows={backups}
                rowKey={(r) => r.label}
                pageSize={10}
                emptyState={
                    <div className="py-8 text-center text-xs text-text-muted">
                        {t(
                            "暂无备份 — 点击右上角创建。",
                            "No backups yet — create one above.",
                        )}
                    </div>
                }
            />

            <div className="mt-6 mb-3">
                <h2 className="text-sm text-text-primary">
                    {t("审计日志（最近 20 条）", "Audit logs (latest 20)")}
                </h2>
            </div>
            <DataTable
                columns={auditColumns}
                rows={audit}
                rowKey={(r) => r.audit_id}
                pageSize={20}
                emptyState={
                    <div className="py-8 text-center text-xs text-text-muted">
                        {t("暂无审计记录。", "No audit records.")}
                    </div>
                }
            />

            <ConfirmDialog
                open={pendingDelete !== ""}
                danger
                title={`${t("删除调度", "Delete schedule")} ${pendingDelete}?`}
                confirmName={pendingDelete}
                description={t(
                    "该调度将被删除，且无法恢复。",
                    "The schedule will be deleted and cannot be recovered.",
                )}
                confirmLabel={t("确认", "Confirm")}
                cancelLabel={t("取消", "Cancel")}
                onConfirm={onDelete}
                onCancel={() => setPendingDelete("")}
            />
            {pendingDecision ? (
                <input
                    value={decisionRemark}
                    onChange={(e) => setDecisionRemark(e.target.value)}
                    placeholder={t("审批备注（可选）", "Remark (optional)")}
                    className="mb-2 w-full rounded-md border border-border bg-bg px-3 py-2 text-sm text-text-primary"
                />
            ) : null}
            <ConfirmDialog
                open={pendingDecision !== null}
                danger={pendingDecision?.decision === "reject"}
                title={
                    pendingDecision
                        ? pendingDecision.decision === "approve"
                            ? `${t("通过", "Approve")} ${pendingDecision.requestId}?`
                            : `${t("驳回", "Reject")} ${pendingDecision.requestId}?`
                        : ""
                }
                description={t(
                    "操作将立即生效并记录审批人与备注。",
                    "The decision takes effect immediately and records the approver and remark.",
                )}
                confirmLabel={t("确认", "Confirm")}
                cancelLabel={t("取消", "Cancel")}
                onConfirm={onDecide}
                onCancel={() => setPendingDecision(null)}
            />
            <ConfirmDialog
                open={pendingRestore !== ""}
                danger
                title={`${t("恢复备份", "Restore backup")} ${pendingRestore}?`}
                confirmName={pendingRestore}
                description={t(
                    "恢复将用备份覆盖当前数据，且无法撤销。",
                    "Restoring overwrites current data with the backup and cannot be undone.",
                )}
                confirmLabel={t("确认", "Confirm")}
                cancelLabel={t("取消", "Cancel")}
                onConfirm={onRestore}
                onCancel={() => setPendingRestore("")}
            />
        </div>
    );
}
