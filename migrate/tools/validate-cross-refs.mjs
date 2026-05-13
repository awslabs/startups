#!/usr/bin/env node

/**
 * Validates cross-references between marketplace manifests and plugin directories
 * for both Claude Code (.claude-plugin/) and Cursor (.cursor-plugin/).
 */

import { promises as fs } from "node:fs";
import path from "node:path";
import process from "node:process";

const repoRoot = process.cwd();
const errors = [];
const warnings = [];

const pluginNamePattern = /^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/;

function addError(msg) { errors.push(msg); }
function addWarning(msg) { warnings.push(msg); }

async function pathExists(p) {
  try { await fs.access(p); return true; } catch { return false; }
}

async function readJson(filePath) {
  try {
    return JSON.parse(await fs.readFile(filePath, "utf8"));
  } catch {
    return null;
  }
}

function isSafeRelativePath(value) {
  if (typeof value !== "string" || value.length === 0) return false;
  if (path.isAbsolute(value)) return false;
  const normalized = path.posix.normalize(value.replace(/\\/g, "/"));
  return !normalized.startsWith("../") && normalized !== "..";
}

async function validateMarketplace(platform, manifestDir, pluginManifestDir) {
  const marketplacePath = path.join(repoRoot, manifestDir, "marketplace.json");
  const marketplace = await readJson(marketplacePath);

  if (!marketplace) {
    addWarning(`${platform}: no marketplace.json found at ${manifestDir}/`);
    return;
  }

  console.log(`\nValidating ${platform} marketplace...`);

  if (typeof marketplace.name !== "string" || !pluginNamePattern.test(marketplace.name)) {
    addError(`${platform}: marketplace "name" must be lowercase kebab-case.`);
  }

  if (!marketplace.owner?.name) {
    addError(`${platform}: marketplace "owner.name" is required.`);
  }

  if (!Array.isArray(marketplace.plugins) || marketplace.plugins.length === 0) {
    addError(`${platform}: marketplace "plugins" must be a non-empty array.`);
    return;
  }

  const seenNames = new Set();
  for (const [i, entry] of marketplace.plugins.entries()) {
    const label = `${platform} plugins[${i}]`;

    if (!entry || typeof entry !== "object") {
      addError(`${label}: must be an object.`);
      continue;
    }

    if (typeof entry.name !== "string" || !pluginNamePattern.test(entry.name)) {
      addError(`${label}: "name" must be lowercase kebab-case.`);
      continue;
    }

    if (seenNames.has(entry.name)) {
      addError(`${label}: duplicate plugin name "${entry.name}".`);
    }
    seenNames.add(entry.name);

    const source = entry.source;
    if (!source || !isSafeRelativePath(source)) {
      addError(`${label}: "source" must be a safe relative path.`);
      continue;
    }

    const pluginDir = path.resolve(repoRoot, source);
    if (!(await pathExists(pluginDir))) {
      addError(`${label}: source directory does not exist: ${source}`);
      continue;
    }

    const pluginJsonPath = path.join(pluginDir, pluginManifestDir, "plugin.json");
    const pluginJson = await readJson(pluginJsonPath);
    if (!pluginJson) {
      addError(`${label}: missing ${pluginManifestDir}/plugin.json in ${source}`);
      continue;
    }

    if (pluginJson.name !== entry.name) {
      addError(`${label}: marketplace name "${entry.name}" does not match plugin.json name "${pluginJson.name}".`);
    }

    console.log(`  OK: ${entry.name} -> ${source}`);
  }
}

async function main() {
  await validateMarketplace("Claude Code", ".claude-plugin", ".claude-plugin");
  await validateMarketplace("Cursor", ".cursor-plugin", ".cursor-plugin");

  if (warnings.length > 0) {
    console.log("\nWarnings:");
    for (const w of warnings) console.log(`  - ${w}`);
  }

  if (errors.length > 0) {
    console.error("\nValidation failed:");
    for (const e of errors) console.error(`  - ${e}`);
    process.exit(1);
  }

  console.log("\nAll cross-references valid.");
}

await main();
