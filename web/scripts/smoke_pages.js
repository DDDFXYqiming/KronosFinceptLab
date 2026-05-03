const pages = [
  { path: "/", label: "KronosFinceptLab" },
  { path: "/forecast", label: "价格预测" },
  { path: "/analysis", label: "AI 分析" },
  { path: "/batch", label: "批量" },
  { path: "/backtest", label: "回测" },
  { path: "/data", label: "数据" },
  { path: "/watchlist", label: "自选股" },
];

const baseUrl = process.env.WEB_SMOKE_BASE_URL || "http://localhost:3000";
const requireApi = process.env.WEB_SMOKE_REQUIRE_API === "1";

function urlFor(path) {
  return new URL(path, baseUrl).toString();
}

async function fetchText(path) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const res = await fetch(urlFor(path), { signal: controller.signal });
    const text = await res.text();
    return { res, text };
  } finally {
    clearTimeout(timeout);
  }
}

async function main() {
  const results = [];

  for (const page of pages) {
    const { res, text } = await fetchText(page.path);
    if (res.status >= 400) {
      throw new Error(`${page.path} returned HTTP ${res.status}`);
    }
    if (!text.includes(page.label) && !text.includes("KronosFinceptLab")) {
      throw new Error(`${page.path} did not render expected shell text`);
    }
    results.push(`${page.path}:${res.status}`);
  }

  const health = await fetch(urlFor("/api/health")).catch((error) => ({ ok: false, status: 0, error }));
  if (!health.ok) {
    const message = `/api/health through Web proxy is not reachable (status=${health.status || 0})`;
    if (requireApi) throw new Error(message);
    console.warn(`${message}; set WEB_SMOKE_REQUIRE_API=1 to fail on this check.`);
  } else {
    results.push("/api/health:200");
  }

  console.log(`Page smoke passed: ${results.join(", ")}`);
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
