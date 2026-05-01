#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { execFileSync, spawnSync } = require("child_process");

const rootDir = path.resolve(__dirname, "..");
const webDir = path.join(rootDir, "web");
const fix = process.argv.includes("--fix");
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";

const swcByPlatform = {
  "darwin:arm64": "@next/swc-darwin-arm64",
  "darwin:x64": "@next/swc-darwin-x64",
  "linux:arm64": "@next/swc-linux-arm64-gnu",
  "linux:x64": "@next/swc-linux-x64-gnu",
  "win32:arm64": "@next/swc-win32-arm64-msvc",
  "win32:ia32": "@next/swc-win32-ia32-msvc",
  "win32:x64": "@next/swc-win32-x64-msvc",
};

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function commandOutput(command, args, cwd) {
  try {
    return execFileSync(command, args, {
      cwd,
      encoding: "utf8",
      shell: process.platform === "win32",
      stdio: ["ignore", "pipe", "pipe"],
    }).trim();
  } catch (error) {
    return null;
  }
}

function findPackageJson(packageName) {
  const packageParts = packageName.split("/");
  const candidates = [
    path.join(webDir, "node_modules", ...packageParts, "package.json"),
    path.join(webDir, "node_modules", "next", "node_modules", ...packageParts, "package.json"),
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || null;
}

function lockEntryExists(lockfile, packageName) {
  if (!lockfile || !lockfile.packages) {
    return false;
  }

  const packagePath = packageName.split("/").join("/");
  return Boolean(
    lockfile.packages[`node_modules/${packagePath}`] ||
      lockfile.packages[`node_modules/next/node_modules/${packagePath}`]
  );
}

function collectState() {
  const packageJsonPath = path.join(webDir, "package.json");
  const lockfilePath = path.join(webDir, "package-lock.json");
  const nextPackagePath = path.join(webDir, "node_modules", "next", "package.json");
  const swcPackage = swcByPlatform[`${process.platform}:${process.arch}`];
  const swcPackagePath = swcPackage ? findPackageJson(swcPackage) : null;

  const packageJson = fs.existsSync(packageJsonPath) ? readJson(packageJsonPath) : null;
  const lockfile = fs.existsSync(lockfilePath) ? readJson(lockfilePath) : null;
  const nextPackage = fs.existsSync(nextPackagePath) ? readJson(nextPackagePath) : null;
  const swcPackageJson = swcPackagePath ? readJson(swcPackagePath) : null;

  return {
    packageJsonPath,
    lockfilePath,
    nextPackagePath,
    swcPackage,
    swcPackagePath,
    packageJson,
    lockfile,
    nextPackage,
    swcPackageJson,
  };
}

function printState(state) {
  const npmVersion = commandOutput(npmCommand, ["--version"], webDir) || "not found";
  const npmRegistry = commandOutput(npmCommand, ["config", "get", "registry"], webDir) || "unknown";
  const lockNextVersion =
    state.lockfile &&
    state.lockfile.packages &&
    state.lockfile.packages["node_modules/next"] &&
    state.lockfile.packages["node_modules/next"].version;

  console.log(`[web] node: ${process.version} (${process.platform}/${process.arch})`);
  console.log(`[web] npm: ${npmVersion}`);
  console.log(`[web] npm registry: ${npmRegistry}`);
  console.log(`[web] package next: ${state.packageJson && state.packageJson.dependencies ? state.packageJson.dependencies.next : "missing"}`);
  console.log(`[web] lockfile next: ${lockNextVersion || "missing"}`);
  console.log(`[web] installed next: ${state.nextPackage ? state.nextPackage.version : "missing"}`);
  console.log(`[web] platform swc: ${state.swcPackage || "unsupported platform"}`);
  console.log(`[web] swc package path: ${state.swcPackagePath || "missing"}`);
  console.log(`[web] swc installed version: ${state.swcPackageJson ? state.swcPackageJson.version : "missing"}`);
}

function validate(state) {
  const problems = [];
  const warnings = [];

  if (!state.packageJson) {
    problems.push("web/package.json is missing.");
  }
  if (!state.lockfile) {
    problems.push("web/package-lock.json is missing.");
  }
  if (!state.nextPackage) {
    problems.push("web/node_modules/next is missing.");
  }
  if (!state.swcPackage) {
    problems.push(`Unsupported Node platform for Next SWC: ${process.platform}/${process.arch}.`);
  }
  if (state.swcPackage && !state.swcPackagePath) {
    problems.push(`Current platform SWC package is missing: ${state.swcPackage}.`);
  }
  if (state.lockfile && state.swcPackage && !lockEntryExists(state.lockfile, state.swcPackage)) {
    problems.push(`package-lock.json does not contain ${state.swcPackage}.`);
  }

  if (state.nextPackage && state.swcPackageJson) {
    const expectedSwcVersion = state.nextPackage.optionalDependencies
      ? state.nextPackage.optionalDependencies[state.swcPackage]
      : null;
    if (expectedSwcVersion && expectedSwcVersion !== state.swcPackageJson.version) {
      problems.push(
        `${state.swcPackage} version mismatch: installed ${state.swcPackageJson.version}, expected ${expectedSwcVersion}.`
      );
    }
  }

  if (state.lockfile && state.nextPackage && state.nextPackage.optionalDependencies) {
    for (const packageName of Object.keys(state.nextPackage.optionalDependencies)) {
      if (!lockEntryExists(state.lockfile, packageName)) {
        warnings.push(`package-lock.json is missing optional cross-platform SWC entry: ${packageName}.`);
      }
    }
  }

  return { problems, warnings };
}

function installOptionalDeps() {
  console.log("[web] running: npm install --include=optional");
  const result = spawnSync(npmCommand, ["install", "--include=optional"], {
    cwd: webDir,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
  return result.status === 0;
}

function printManualFix() {
  console.error("");
  console.error("[web] Automatic dependency recovery did not complete.");
  console.error("[web] Run these commands from the repository root:");
  console.error("  cd web");
  console.error("  rmdir /s /q node_modules");
  console.error("  npm install --include=optional");
}

function main() {
  if (!fs.existsSync(webDir)) {
    console.error(`[web] Web directory not found: ${webDir}`);
    process.exit(1);
  }

  let state = collectState();
  printState(state);
  let { problems, warnings } = validate(state);

  for (const warning of warnings) {
    console.warn(`[web] warning: ${warning}`);
  }

  if (problems.length > 0 && fix) {
    for (const problem of problems) {
      console.warn(`[web] problem: ${problem}`);
    }
    if (!installOptionalDeps()) {
      printManualFix();
      process.exit(1);
    }

    state = collectState();
    console.log("[web] re-checking dependencies after npm install...");
    printState(state);
    ({ problems, warnings } = validate(state));
    for (const warning of warnings) {
      console.warn(`[web] warning: ${warning}`);
    }
  }

  if (problems.length > 0) {
    for (const problem of problems) {
      console.error(`[web] problem: ${problem}`);
    }
    printManualFix();
    process.exit(1);
  }

  console.log("[web] dependency health check passed.");
  console.log("[web] start.bat sets NEXT_IGNORE_INCORRECT_LOCKFILE=1 after verifying the installed platform SWC package.");
}

main();
