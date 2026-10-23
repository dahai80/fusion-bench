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

async function getJson<T>(path: string): Promise<T> {
    const resp = await fetch(path, { headers: headers() });
    if (!resp.ok) {
        throw new Error(`GET ${path} failed: ${resp.status}`);
    }
    return (await resp.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
    const resp = await fetch(path, {
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
