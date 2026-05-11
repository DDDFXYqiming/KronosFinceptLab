const INTERNAL_API_URL = process.env.INTERNAL_API_URL || "http://localhost:8000";
const API_PROXY_TIMEOUT_MS = Number(process.env.API_PROXY_TIMEOUT_MS || 120000);
const DEFAULT_MAX_BODY_BYTES = 1024 * 1024;

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

type RouteContext = {
  params: Promise<{
    path?: string[];
  }>;
};

type AuthDecision = {
  allowed: boolean;
  status: number;
  error?: string;
  type?: string;
};

function splitKeys(value: string | undefined): string[] {
  return (value || "")
    .split(/[,\n\r\t ]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function envFlag(name: string): boolean {
  return ["1", "true", "yes", "on"].includes((process.env[name] || "").trim().toLowerCase());
}

function maxBodyBytes(): number {
  const raw = Number(process.env.KRONOS_MAX_BODY_BYTES || process.env.API_PROXY_MAX_BODY_BYTES || DEFAULT_MAX_BODY_BYTES);
  return Number.isFinite(raw) && raw > 0 ? raw : DEFAULT_MAX_BODY_BYTES;
}

function isPublicPath(path: string[] | undefined): boolean {
  return (path || []).join("/") === "health";
}

function requiresAdmin(path: string[] | undefined): boolean {
  return (path || [])[0] === "alert";
}

function extractClientKey(request: Request): string | null {
  const explicit = request.headers.get("X-Kronos-Api-Key")?.trim();
  if (explicit) return explicit;
  const auth = request.headers.get("Authorization") || "";
  const prefix = "bearer ";
  if (auth.toLowerCase().startsWith(prefix)) {
    return auth.slice(prefix.length).trim() || null;
  }
  return null;
}

function keyRole(key: string): "admin" | "user" | null {
  if (splitKeys(process.env.KRONOS_ADMIN_API_KEYS).includes(key)) return "admin";
  if (splitKeys(process.env.KRONOS_API_KEYS).includes(key)) return "user";
  return null;
}

function chooseInternalKey(): string | null {
  return (
    process.env.KRONOS_INTERNAL_API_KEY?.trim() ||
    splitKeys(process.env.KRONOS_INTERNAL_API_KEYS)[0] ||
    splitKeys(process.env.KRONOS_ADMIN_API_KEYS)[0] ||
    splitKeys(process.env.KRONOS_API_KEYS)[0] ||
    null
  );
}

function checkProxyAuth(request: Request, path: string[] | undefined): AuthDecision {
  if (isPublicPath(path)) return { allowed: true, status: 200 };
  if (envFlag("KRONOS_AUTH_DISABLED")) return { allowed: true, status: 200 };

  const key = extractClientKey(request);
  if (!key) {
    return { allowed: false, status: 401, error: "API key is required", type: "auth_required" };
  }
  const role = keyRole(key);
  if (!role) {
    return { allowed: false, status: 401, error: "Invalid API key", type: "invalid_api_key" };
  }
  if (requiresAdmin(path) && role !== "admin") {
    return { allowed: false, status: 403, error: "Admin API key is required", type: "admin_required" };
  }
  return { allowed: true, status: 200 };
}

function checkContentLength(request: Request): Response | null {
  const method = request.method.toUpperCase();
  if (method === "GET" || method === "HEAD") return null;
  const raw = request.headers.get("Content-Length");
  if (!raw) return null;
  const length = Number(raw);
  const limit = maxBodyBytes();
  if (Number.isFinite(length) && length > limit) {
    return Response.json(
      { ok: false, error: `Request body too large; limit is ${limit} bytes`, type: "body_too_large" },
      { status: 413 }
    );
  }
  return null;
}

function buildTargetUrl(request: Request, path: string[] | undefined): string {
  const incoming = new URL(request.url);
  const apiPath = (path || []).map(encodeURIComponent).join("/");
  const target = new URL(`${INTERNAL_API_URL.replace(/\/$/, "")}/api/${apiPath}`);
  target.search = incoming.search;
  return target.toString();
}

function buildProxyHeaders(request: Request): Headers {
  const headers = new Headers();
  const internalKey = chooseInternalKey();
  for (const name of ["Accept", "Content-Type", "X-Request-ID", "X-Test-Run-ID", "User-Agent", "X-Forwarded-For"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (internalKey) {
    headers.set("X-Kronos-Internal-Key", internalKey);
  }
  return headers;
}

async function readBoundedBody(request: Request): Promise<ArrayBuffer | undefined | Response> {
  const method = request.method.toUpperCase();
  if (method === "GET" || method === "HEAD") return undefined;
  const body = await request.arrayBuffer();
  const limit = maxBodyBytes();
  if (body.byteLength > limit) {
    return Response.json(
      { ok: false, error: `Request body too large; limit is ${limit} bytes`, type: "body_too_large" },
      { status: 413 }
    );
  }
  return body;
}

async function proxy(request: Request, context: RouteContext): Promise<Response> {
  const params = await context.params;
  const path = params.path;
  const oversized = checkContentLength(request);
  if (oversized) return oversized;

  const auth = checkProxyAuth(request, path);
  if (!auth.allowed) {
    return Response.json({ ok: false, error: auth.error, type: auth.type }, { status: auth.status });
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), API_PROXY_TIMEOUT_MS);
  try {
    const method = request.method.toUpperCase();
    const body = await readBoundedBody(request);
    if (body instanceof Response) return body;
    const upstream = await fetch(buildTargetUrl(request, path), {
      method,
      headers: buildProxyHeaders(request),
      body,
      signal: controller.signal,
      cache: "no-store",
    });

    const headers = new Headers(upstream.headers);
    headers.delete("content-encoding");
    headers.delete("content-length");
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers,
    });
  } catch (error) {
    const aborted = error instanceof DOMException && error.name === "AbortError";
    return Response.json(
      {
        error: aborted ? "API proxy timeout" : "API proxy failed",
        type: aborted ? "api_proxy_timeout" : "api_proxy_error",
      },
      { status: aborted ? 504 : 502 }
    );
  } finally {
    clearTimeout(timeoutId);
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
