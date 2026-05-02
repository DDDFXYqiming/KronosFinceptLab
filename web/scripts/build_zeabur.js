const { spawnSync } = require("child_process");
const path = require("path");

process.env.NEXT_IGNORE_INCORRECT_LOCKFILE = "1";
process.env.NEXT_TELEMETRY_DISABLED = "1";

const nextBin = process.platform === "win32"
  ? path.join("node_modules", ".bin", "next.cmd")
  : path.join("node_modules", ".bin", "next");

const result = spawnSync(nextBin, ["build"], {
  stdio: "inherit",
  shell: process.platform === "win32",
  env: process.env,
});

process.exit(result.status === null ? 1 : result.status);
