export type Role = "admin" | "coordinator" | "reviewer" | "applicant";
export interface User { id: string; email: string; name: string; organisation: string; roles: Role[] }
export interface Session { user: User | null; csrf: string | null; set_up: boolean }
export interface Job {
  id: string; kind: string; status: "queued" | "running" | "done" | "failed";
  progress: number; message: string; error: string | null;
}
export interface Project {
  id: string; name: string; created: string; updated: string; curator: string;
  plan: string | null; requirements: string | null;
  analysed: boolean; checked: boolean; has_drafts: boolean; active_jobs: Job[];
  rules: { total?: number; error?: string };
}
export interface Member { id: string; email: string; name: string; roles: Role[]; active: boolean }

export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

let csrf = "";
let onSignedOut: () => void = () => {};
export const setCsrf = (value: string | null) => { csrf = value ?? ""; };
export const whenSignedOut = (fn: () => void) => { onSignedOut = fn; };

export async function api<T>(path: string, init: { method?: string; json?: unknown; form?: FormData } = {}): Promise<T> {
  const method = init.method ?? "GET";
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["x-rp-csrf"] = csrf;
  let body: BodyInit | undefined = init.form;
  if (init.json !== undefined) { headers["content-type"] = "application/json"; body = JSON.stringify(init.json); }
  let response: Response;
  try {
    response = await fetch(path, { method, headers, body, credentials: "same-origin" });
  } catch {
    throw new ApiError("The server cannot be reached. Check your connection and try again.", 0);
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/api/auth/")) onSignedOut();
    const detail = typeof data?.detail === "string" ? data.detail : "The request was not accepted.";
    throw new ApiError(detail, response.status);
  }
  return data as T;
}

export const has = (user: User, ...roles: Role[]) => roles.some((r) => user.roles.includes(r));
