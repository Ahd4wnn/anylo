// Thin fetch client. Access token lives in memory only; the refresh token is an httpOnly cookie.
const BASE = import.meta.env.VITE_API_BASE_URL ?? "/v1";

let accessToken: string | null = null;
let shopId: string | null = null;
type RefreshResult = "ok" | "invalid" | "network";
let refreshing: Promise<RefreshResult> | null = null;
const channel = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel("anylo-auth") : null;

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public fields?: Record<string, unknown>) {
    super(message);
  }
}

export const session = {
  set(token: string | null) { accessToken = token; },
  get token() { return accessToken; },
  setShop(id: string | null) { shopId = id; },
};

async function parse(res: Response): Promise<unknown> {
  if (res.status === 204) return null;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const b = body as { detail?: unknown; code?: string; fields?: Record<string, unknown> };
    // FastAPI validation errors arrive as a list; show a friendly message instead.
    const msg = typeof b.detail === "string" ? b.detail : "Please check the highlighted fields.";
    throw new ApiError(res.status, b.code ?? (res.status === 422 ? "validation" : "error"), msg, b.fields);
  }
  return body;
}

async function tryRefresh(): Promise<RefreshResult> {
  refreshing ??= fetch(`${BASE}/auth/refresh`, { method: "POST", credentials: "include" })
    .then(async (r): Promise<RefreshResult> => {
      if (r.status === 401) return "invalid";
      if (!r.ok) return "network"; // server hiccup or proxy error: keep the session
      accessToken = ((await r.json()) as { access_token: string }).access_token;
      return "ok";
    })
    .catch((): RefreshResult => "network")
    .finally(() => { refreshing = null; });
  return refreshing;
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.json !== undefined) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (shopId) headers.set("X-Shop-Id", shopId);
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init, headers, credentials: "include",
      body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
    });
  } catch {
    throw new ApiError(0, "network", "Can't reach Anylo. Check your internet connection.");
  }
  if (res.status === 401 && retry && !path.startsWith("/auth/")) {
    const r = await tryRefresh();
    if (r === "ok") return api<T>(path, init, false);
    if (r === "invalid") channel?.postMessage("logout");
  }
  return parse(res) as Promise<T>;
}

export const onRemoteLogout = (fn: () => void) => channel?.addEventListener("message", (e) => e.data === "logout" && fn());
export const restoreSession = tryRefresh;
