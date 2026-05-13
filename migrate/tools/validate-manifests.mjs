#!/usr/bin/env node

/**
 * Validates JSON manifests for all platforms:
 * - Claude Code: .claude-plugin/marketplace.json, plugin.json, .mcp.json
 * - Cursor: .cursor-plugin/marketplace.json, plugin.json, mcp.json
 * - Kiro: mcp.json
 *
 * Checks: valid JSON, required fields present, naming conventions.
 */

import { promises as fs } from "node:fs";
import path from "node:path";
import process from "node:process";

const repoRoot = process.cwd();
const errors = [];

function addError(msg) { errors.push(msg); }

async function readJson(filePath, label) {
  let raw;
  try {
    raw = await fs.readFile(filePath, "utf8");
  } catch {
    return null;
  }
  try {
    return JSON.parse(raw);
  } catch (e) {
    addError(`${label}: invalid JSON — ${e.message}`);
    return null;
  }
}

async function findFiles(dir, pattern) {
  const results = [];
  try {
    const entries = await fs.readdir(dir, { withFileTypes: true, recursive: true });
    for (const entry of entries) {
      const full = path.join(entry.parentPath || dir, entry.name);
      if (entry.isFile() && entry.name === pattern) {
        results.push(full);
      }
    }
  } catch { /* dir doesn't exist */ }
  return results;
}

const namePattern = /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/;

async function validatePluginJson(filePath, platform) {
  const rel = path.relative(repoRoot, filePath);
  const json = await readJson(filePath, `${platform} ${rel}`);
  if (!json) return;

  if (!json.name || !namePattern.test(json.name)) {
    addError(`${rel}: "name" must be lowercase kebab-case.`);
  }
  if (!json.description) {
    addError(`${rel}: "description" is required.`);
  }
}

async function validateMcpJson(filePath, platform) {
  const rel = path.relative(repoRoot, filePath);
  const json = await readJson(filePath, `${platform} ${rel}`);
  if (!json) return;

  if (!json.mcpServers || typeof json.mcpServers !== "object") {
    addError(`${rel}: must contain "mcpServers" object.`);
    return;
  }

  for (const [name, config] of Object.entries(json.mcpServers)) {
    const type = config.type || "stdio";
    if (type === "stdio" && !config.command) {
      addError(`${rel}: server "${name}" is stdio but missing "command".`);
    }
    if (type === "http" && !config.url) {
      addError(`${rel}: server "${name}" is http but missing "url".`);
    }
  }
}

async function main() {
  console.log("Validating manifests...\n");

  const claudeMarketplace = path.join(repoRoot, ".claude-plugin", "marketplace.json");
  await readJson(claudeMarketplace, "Claude Code marketplace");

  const cursorMarketplace = path.join(repoRoot, ".cursor-plugin", "marketplace.json");
  await readJson(cursorMarketplace, "Cursor marketplace");

  const claudePlugins = await findFiles(path.join(repoRoot, "features"), "plugin.json");
  for (const f of claudePlugins) {
    if (f.includes(".claude-plugin")) await validatePluginJson(f, "Claude Code");
    if (f.includes(".cursor-plugin")) await validatePluginJson(f, "Cursor");
  }

  const mcpFiles = [
    ...(await findFiles(path.join(repoRoot, "features"), ".mcp.json")),
    ...(await findFiles(path.join(repoRoot, "features"), "mcp.json")),
  ];
  for (const f of mcpFiles) {
    const platform = f.includes("/claude-code/") ? "Claude Code"
      : f.includes("/cursor/") ? "Cursor"
      : f.includes("/kiro/") ? "Kiro"
      : "Unknown";
    await validateMcpJson(f, platform);
  }

  if (errors.length > 0) {
    console.error("Manifest validation failed:");
    for (const e of errors) console.error(`  - ${e}`);
    process.exit(1);
  }

  console.log("All manifests valid.");
}

await main();
