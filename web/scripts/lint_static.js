const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const srcRoot = path.join(root, "src");

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function walk(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) return walk(fullPath);
    return [fullPath];
  });
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const appFiles = walk(path.join(srcRoot, "app")).filter((file) => /\.(ts|tsx)$/.test(file));
const sourceFiles = walk(srcRoot).filter((file) => /\.(ts|tsx|css)$/.test(file));
const source = new Map(sourceFiles.map((file) => [file, fs.readFileSync(file, "utf8")]));

for (const file of appFiles) {
  const content = source.get(file);
  const rel = path.relative(root, file).replace(/\\/g, "/");
  assert(!/from\s+["']recharts["']/.test(content), `${rel} must not import recharts in app routes`);
  assert(!/text-3xl\s+font-display/.test(content), `${rel} uses a desktop-only title size`);
}

const pages = [
  "src/app/page.tsx",
  "src/app/forecast/page.tsx",
  "src/app/analysis/page.tsx",
  "src/app/batch/page.tsx",
  "src/app/backtest/page.tsx",
  "src/app/data/page.tsx",
  "src/app/watchlist/page.tsx",
];

for (const page of pages) {
  const content = read(page);
  assert(content.includes("page-shell"), `${page} must use the shared page shell`);
  assert(content.includes("page-title"), `${page} must use the shared page title`);
}

const globals = read("src/app/globals.css");
assert(globals.includes("min-height: 44px"), "global controls must keep mobile touch targets >= 44px");
assert(globals.includes("table-scroll"), "global styles must include bounded table scrolling");
assert(globals.includes("chart-frame"), "global styles must include bounded chart frames");

const header = read("src/components/layout/Header.tsx");
assert(header.includes('role="dialog"'), "mobile navigation must expose dialog semantics");
assert(header.includes("mobile-safe-top"), "mobile header must use safe-area top spacing");
assert(header.includes("mobile-safe-bottom"), "mobile drawer must use safe-area bottom spacing");

const sidebar = read("src/components/layout/Sidebar.tsx");
assert(sidebar.includes("hidden h-screen"), "desktop sidebar must stay hidden on mobile");
assert(sidebar.includes("md:block"), "desktop sidebar must only render in desktop flow");

console.log("Static frontend lint passed.");
