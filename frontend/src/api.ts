// Thin client for the FastAPI backend. All routes live under /api.
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function call<T = any>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch('/api' + path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json();
}

export const api = {
  get: <T = any>(p: string) => call<T>('GET', p),
  post: <T = any>(p: string, b: unknown = {}) => call<T>('POST', p, b),
  put: <T = any>(p: string, b: unknown) => call<T>('PUT', p, b),
};

export type Step = { seq: number; kind: string; system: string; title: string; text: string; payload: any; at: number };
export type Run = {
  id: number; title: string; status: string; mode: string; trigger: any; started_at: string; ended_at: string | null;
  pending: any; result: any; options: { k: string; label: string }[] | null; step_count: number; steps?: Step[];
};
export type Status = {
  today: string; today_label: string; ai_available: boolean; model: string | null; ai_mode: string; ai_active: boolean;
  counts: { unprocessed: number; waiting_person: number; approvals: number; proposals: number; replies: number; cases_open: number; running: number; runs: number };
  running: { id: number; title: string; step: string | null } | null;
};
