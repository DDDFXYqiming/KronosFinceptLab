const INTERNAL_API_URL = process.env.INTERNAL_API_URL || "http://localhost:8000";
const API_PROXY_TIMEOUT_MS = Number(process.env.API_PROXY_TIMEOUT_MS || 120000);

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

type RouteContext = {
  params: {
    path?: string[];
  };
};

function buildTargetUrl(request: Request, path: string[] | undefined): string {
  const incoming = new URL(request.url);
  const apiPath = (path || []).map(encodeURIComponent).join("/");
  const target = new URL(`${INTERNAL_API_URL.replace(/\/$/, "")}/api/${apiPath}`);
  target.search = incoming.search;
  return target.toString();
}

function buildProxyHeaders(request: Request): Headers {
  const headers = new Headers(request.headers);
  for (const name of ["host", "connection", "content-length", "accept-encoding"]) {
    headers.delete(name);
  }
  return headers;
}

async function proxy(request: Request, context: RouteContext): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), API_PROXY_TIMEOUT_MS);
  try {
    const method = request.method.toUpperCase();
    const body = method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer();
    const upstream = await fetch(buildTargetUrl(request, context.params.path), {
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
