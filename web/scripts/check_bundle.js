const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const expectedRoutes = [
  "/page",
  "/forecast/page",
  "/analysis/page",
  "/batch/page",
  "/backtest/page",
  "/data/page",
  "/watchlist/page",
];

function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(root, relativePath), "utf8"));
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function fileSize(relativePath) {
  const fullPath = path.join(root, ".next", relativePath);
  return fs.existsSync(fullPath) ? fs.statSync(fullPath).size : 0;
}

try {
  assert(fs.existsSync(path.join(root, ".next", "app-build-manifest.json")), "Run npm run build:zeabur before check:bundle");
  assert(fs.existsSync(path.join(root, ".next", "standalone")), "Next standalone output is missing");

  const manifest = readJson(".next/app-build-manifest.json");
  const pages = manifest.pages || {};
  const routeLines = [];

  for (const route of expectedRoutes) {
    const chunks = pages[route];
    assert(Array.isArray(chunks), `Build manifest is missing route ${route}`);
    const totalBytes = chunks.reduce((sum, chunk) => sum + fileSize(chunk), 0);
    const kb = (totalBytes / 1024).toFixed(1);
    routeLines.push(`${route}: ${kb} kB raw route chunks`);
    assert(totalBytes < 5 * 1024 * 1024, `${route} route chunks exceed 5 MB raw`);
  }

  console.log("Bundle/build check passed.");
  console.log("First Load JS guard (raw route chunk estimate):");
  for (const line of routeLines) {
    console.log(`- ${line}`);
  }
} catch (error) {
  console.error(error.message || error);
  process.exit(1);
}
