// issue #23: fusion-bench REST API client (:11467). Same-origin fetch —
// standalone dev goes through the vite proxy, embedded through the gateway
// /shell/fusion-bench/ proxy.
//
// Auth (#16): the API is fail-closed behind fusion-identity JWTs — every
// request needs X-Tenant-Id + Authorization: Bearer. The UI has NO auth
// logic (spec): embedded mode the shell session injects both headers
// upstream; standalone dev wires them from VITE_BENCH_TENANT /
// VITE_BENCH_TOKEN (dev convenience only).
const TENANT: string | undefined = import.meta.env.VITE_BENCH_TENANT;
const TOKEN: string | undefined = import.meta.env.VITE_BENCH_TOKEN;

export interface TaskSummary {
    task_id: string;
    status: string;
    model: string;
    executor_key: string;
    level: string;
    created_at: string;
}

export interface TaskDetail extends TaskSummary {
    progress: number;
    result: Record<string, unknown> | null;
    error: string | null;
    duration_seconds: number;
}

export interface TrendPoint {
    timestamp: string;
    metric_value: number;
    model: string;
    executor_key: string;
}

export interface CompareRow {
    task_id: string;
    result: Record<string, unknown> | null;
}

function headers(): Record<string, string> {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (TENANT) h["X-Tenant-Id"] = TENANT;
    if (TOKEN) h.Authorization = `Bearer ${TOKEN}`;
    return h;
}

// #38: keep API calls inside the module proxy path. Embedded mode serves
// the SPA under /shell/fusion-bench/ — a root-relative /api/... escapes to
// the gateway's own API surface (401). Standalone dev runs at "/" so the
// base resolves to "" and the vite proxy handles /api as before.
function apiBase(): string {
    let p = window.location.pathname;
    if (!p.endsWith("/index.html")) {
        p = p.endsWith("/") ? p : `${p}/`;
    }
    let base = p.endsWith("/") ? p.slice(0, -1) : p;
    if (base.endsWith("/index.html")) {
        base = base.slice(0, -"/index.html".length);
    }
    return base;
}

async function getJson<T>(path: string): Promise<T> {
    const resp = await fetch(`${apiBase()}${path}`, { headers: headers() });
    if (!resp.ok) {
        throw new Error(`GET ${path} failed: ${resp.status}`);
    }
    return (await resp.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
    const resp = await fetch(`${apiBase()}${path}`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify(body ?? {}),
    });
    if (!resp.ok) {
        const detail = (await resp.json().catch(() => null)) as {
            detail?: string;
        } | null;
        throw new Error(
            detail?.detail ?? `POST ${path} failed: ${resp.status}`,
        );
    }
    return (await resp.json()) as T;
}

export async function fetchModels(): Promise<string[]> {
    const data = await getJson<{ models: string[] }>("/api/v1/models");
    return data.models ?? [];
}

export async function fetchTasks(
    page = 1,
    pageSize = 20,
): Promise<TaskSummary[]> {
    return getJson<TaskSummary[]>(
        `/api/v1/tasks?page=${page}&page_size=${pageSize}`,
    );
}

export async function fetchTask(taskId: string): Promise<TaskDetail> {
    return getJson<TaskDetail>(`/api/v1/tasks/${encodeURIComponent(taskId)}`);
}

export async function fetchTrend(limit = 50): Promise<TrendPoint[]> {
    return getJson<TrendPoint[]>(`/api/v1/results/trend?limit=${limit}`);
}

export async function fetchCompare(taskIds: string[]): Promise<CompareRow[]> {
    const v = await postJson<{ compared: CompareRow[] }>(
        "/api/v1/results/compare",
        { task_ids: taskIds },
    );
    return v.compared ?? [];
}

export interface SubmitInput {
    model: string;
    executor_key: string;
    level: string;
    suite?: string;
    max_samples?: number;
    timeout_seconds?: number;
}

export async function submitTask(input: SubmitInput): Promise<TaskSummary> {
    return postJson<TaskSummary>("/api/v1/tasks", input);
}

export async function cancelTask(taskId: string): Promise<void> {
    await postJson(`/api/v1/tasks/${encodeURIComponent(taskId)}/cancel`, {});
}

export async function retryTask(taskId: string): Promise<TaskSummary> {
    return postJson<TaskSummary>(
        `/api/v1/tasks/${encodeURIComponent(taskId)}/retry`,
        {},
    );
}

// ── #39: judge / baseline / schedule / approval surfaces ────────────

export interface Judge {
    name: string;
    model: string;
    judge_type: string;
    weight: number;
    temperature: number;
    max_tokens: number;
    created_at: string;
}

export interface JudgeInput {
    name: string;
    model: string;
    judge_type: string;
    weight: number;
    temperature: number;
}

export async function fetchJudges(): Promise<Judge[]> {
    const data = await getJson<{ judges: Judge[] }>("/api/v1/judges");
    return data.judges ?? [];
}

export async function createJudge(input: JudgeInput): Promise<void> {
    await postJson("/api/v1/judges", input);
}

export async function deleteJudge(name: string): Promise<void> {
    await fetchJson(`/api/v1/judges/${encodeURIComponent(name)}`, "DELETE");
}

export interface Baseline {
    baseline_id: string;
    name: string;
    model: string;
    executor_key: string;
    level: string;
    metrics: Record<string, number>;
    created_at: string;
}

export interface BaselineInput {
    name: string;
    model: string;
    executor_key: string;
    level: string;
}

export async function fetchBaselines(): Promise<Baseline[]> {
    const data = await getJson<{ baselines: Baseline[] }>("/api/v1/baselines");
    return data.baselines ?? [];
}

export async function createBaseline(input: BaselineInput): Promise<void> {
    await postJson("/api/v1/baselines", input);
}

export async function deleteBaseline(name: string): Promise<void> {
    await fetchJson(`/api/v1/baselines/${encodeURIComponent(name)}`, "DELETE");
}

export async function seedBaselines(): Promise<number> {
    const data = await postJson<{ seeded: string[]; count: number }>(
        "/api/v1/baselines/seed",
        {},
    );
    return data.count ?? 0;
}

export interface BaselineDiff {
    baseline_name: string;
    baseline_found: boolean;
    diffs: Record<
        string,
        {
            baseline: number | null;
            current: number | null;
            delta: number | null;
            delta_pct: number | null;
            direction: string;
        }
    >;
}

export async function diffBaseline(
    name: string,
    input: {
        model: string;
        executor_key: string;
        level: string;
        current_metrics: Record<string, number>;
    },
): Promise<BaselineDiff> {
    return postJson<BaselineDiff>(
        `/api/v1/baselines/${encodeURIComponent(name)}/diff`,
        input,
    );
}

export interface Schedule {
    schedule_id: string;
    name: string;
    cron: string;
    model: string;
    executor_key: string;
    level: string;
    enabled: boolean;
}

export interface ScheduleInput {
    name: string;
    cron: string;
    model: string;
    executor_key: string;
    level: string;
}

export async function fetchSchedules(): Promise<Schedule[]> {
    const data = await getJson<{ schedules: Schedule[] }>("/api/v1/schedules");
    return data.schedules ?? [];
}

export async function createSchedule(input: ScheduleInput): Promise<void> {
    await postJson("/api/v1/schedules", input);
}

export async function toggleSchedule(scheduleId: string): Promise<boolean> {
    const data = await fetchJson<{ enabled: boolean }>(
        `/api/v1/schedules/${encodeURIComponent(scheduleId)}/toggle`,
        "PUT",
    );
    return data.enabled;
}

export async function deleteSchedule(scheduleId: string): Promise<void> {
    await fetchJson(
        `/api/v1/schedules/${encodeURIComponent(scheduleId)}`,
        "DELETE",
    );
}

export interface Approval {
    request_id: string;
    gate_id: string;
    gate_name: string;
    metric_name: string;
    metric_value: number;
    threshold: number;
    requester: string;
    status: string;
}

export async function fetchApprovals(pendingOnly = false): Promise<Approval[]> {
    const data = await getJson<{ approvals: Approval[] }>(
        `/api/v1/approvals${pendingOnly ? "?status=pending" : ""}`,
    );
    return data.approvals ?? [];
}

export async function decideApproval(
    requestId: string,
    decision: "approve" | "reject",
    approver: string,
    remark: string,
): Promise<void> {
    await fetchJson(
        `/api/v1/approvals/${encodeURIComponent(requestId)}/${decision}`,
        "PUT",
        {
            approver,
            remark,
        },
    );
}

async function fetchJson<T>(
    path: string,
    method: string,
    body?: unknown,
): Promise<T> {
    const resp = await fetch(`${apiBase()}${path}`, {
        method,
        headers: headers(),
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!resp.ok) {
        throw new Error(`${method} ${path} failed: ${resp.status}`);
    }
    return (await resp.json()) as T;
}
