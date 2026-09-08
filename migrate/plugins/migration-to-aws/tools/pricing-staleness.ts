// pricing-staleness.ts — surface stale pricing caches before users do.
//
// WHY: the estimate phases price from vendored caches (`aws-infra-pricing.json`,
// the per-skill markdown rate cards). Every cache declares its own freshness
// contract — JSON caches carry `_meta.last_updated` + `_meta.staleness_days`,
// markdown caches carry a `**Last updated:** YYYY-MM-DD` line and document a
// 30-day window — but nothing enforced it: caches have quietly crossed their own
// threshold and every estimate silently degraded to `cached_fallback` accuracy.
// This check reads each cache's OWN declared date and window and reports drift.
//
// Modes:
//   node pricing-staleness.ts            # report; ALWAYS exit 0 (safe in `build`
//                                        # — a stale cache must not fail unrelated PRs)
//   node pricing-staleness.ts --strict   # exit 1 when any cache is stale (for a
//                                        # scheduled freshness workflow)
//
// Zero-dep: runs under Node 24 native TS type-stripping (same as the other tools).

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const strict = process.argv.includes("--strict");
const PLUGIN = "migrate/plugins/migration-to-aws";
const SKILLS = join(PLUGIN, "skills");
const DEFAULT_WINDOW_DAYS = 30;

type CacheStatus = { path: string; lastUpdated: string | null; windowDays: number; staleDays: number };

/** Recursively list files under a dir (paths relative to it), or [] when absent. */
function walk(root: string, rel = ""): string[] {
  const abs = join(root, rel);
  if (!existsSync(abs)) return [];
  const out: string[] = [];
  for (const entry of readdirSync(abs)) {
    const r = rel ? join(rel, entry) : entry;
    if (statSync(join(root, r)).isDirectory()) out.push(...walk(root, r));
    else out.push(r);
  }
  return out;
}

function daysSince(isoDate: string): number {
  const then = Date.parse(`${isoDate}T00:00:00Z`);
  return Math.floor((Date.now() - then) / 86_400_000);
}

const caches: CacheStatus[] = [];

for (const rel of walk(SKILLS)) {
  const path = join(SKILLS, rel);
  if (rel.endsWith("aws-infra-pricing.json")) {
    try {
      const meta = (JSON.parse(readFileSync(path, "utf8"))["_meta"] ?? {}) as {
        last_updated?: string;
        staleness_days?: number;
      };
      const windowDays = typeof meta.staleness_days === "number" ? meta.staleness_days : DEFAULT_WINDOW_DAYS;
      const lastUpdated = typeof meta.last_updated === "string" ? meta.last_updated : null;
      caches.push({
        path,
        lastUpdated,
        windowDays,
        staleDays: lastUpdated ? Math.max(0, daysSince(lastUpdated) - windowDays) : -1,
      });
    } catch {
      caches.push({ path, lastUpdated: null, windowDays: DEFAULT_WINDOW_DAYS, staleDays: -1 });
    }
  } else if (/pricing-cache\.md$/.test(rel) || rel.endsWith("heroku-pricing-cache.md")) {
    const m = readFileSync(path, "utf8").match(/\*\*Last updated:\*\*\s*(\d{4}-\d{2}-\d{2})/);
    const lastUpdated = m ? m[1] : null;
    caches.push({
      path,
      lastUpdated,
      windowDays: DEFAULT_WINDOW_DAYS,
      staleDays: lastUpdated ? Math.max(0, daysSince(lastUpdated) - DEFAULT_WINDOW_DAYS) : -1,
    });
  }
}

let staleCount = 0;
for (const c of caches) {
  if (c.lastUpdated === null) {
    console.log(`pricing cache: NO DATE FOUND  ${c.path} — cannot assess freshness`);
    staleCount++;
  } else if (c.staleDays > 0) {
    console.log(
      `pricing cache: STALE  ${c.path} — last updated ${c.lastUpdated}, ` +
        `${c.staleDays} day(s) past its own ${c.windowDays}-day window (estimates degrade to fallback accuracy)`,
    );
    staleCount++;
  } else {
    console.log(`pricing cache: fresh  ${c.path} (last updated ${c.lastUpdated}, window ${c.windowDays}d)`);
  }
}

if (caches.length === 0) console.log("pricing staleness: no pricing caches found");
else if (staleCount > 0) {
  console.log(`pricing staleness: ${staleCount}/${caches.length} cache(s) stale or unassessable`);
} else {
  console.log(`pricing staleness: OK (${caches.length} cache(s) fresh)`);
}

// ---------------------------------------------------------------------------
// Drift check: bedrock_pricing.py's STATIC_FALLBACK vs the markdown rate card.
//
// WHY: the two hold the SAME facts in different units — STATIC_FALLBACK is
// per-1K USD, the cache table is per-1M USD — with nothing keeping them in sync.
// A row was silently copied from Opus 4.1's legacy $15/$75 onto Opus 4.8 ($5/$25),
// making every Opus 4.8 estimate 3x too high. STATIC_FALLBACK is consulted FIRST
// in lookup() (before the PriceList API), so a wrong row is the primary source,
// not a last resort. This asserts per-1K == per-1M / 1000 for every shared model.
// ---------------------------------------------------------------------------

const FALLBACK_TABLE = join(SKILLS, "llm-to-bedrock/scripts/bedrock_pricing.py");
const RATE_CARD = join(SKILLS, "gcp-to-aws/references/shared/pricing-cache.md");

/** Reduce a Bedrock model id to its comparable base: drop the region/inference-profile
 * prefix, the `:N` and `-vN` version suffixes, and the `-YYYYMMDD` date stamp. */
function baseModelId(id: string): string {
  return id
    .trim()
    .replace(/^(us|eu|apac|global)\./, "")
    .replace(/:\d+$/, "")
    .replace(/-v\d+$/, "")
    .replace(/-\d{8}$/, "");
}

const near = (a: number, b: number) => Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b));

let driftCount = 0;
if (!existsSync(FALLBACK_TABLE) || !existsSync(RATE_CARD)) {
  console.log(`pricing drift: SKIPPED — ${FALLBACK_TABLE} or ${RATE_CARD} not found`);
} else {
  // Rate card: `| Name | model-id | Provider | input $/1M | output $/1M | ... |`.
  // A base id appearing twice with DIFFERENT rates (e.g. a long-context variant) is
  // ambiguous — record it and skip rather than assert against an arbitrary row.
  const card = new Map<string, { input: number; output: number }>();
  const ambiguous = new Set<string>();
  for (const line of readFileSync(RATE_CARD, "utf8").split("\n")) {
    const m = line.match(/^\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|/);
    if (!m) continue;
    const id = m[2].trim();
    const input = Number(m[4].trim());
    const output = Number(m[5].trim());
    if (!/^[a-z0-9]+\.[a-z0-9.\-:]+$/.test(id) || !Number.isFinite(input) || !Number.isFinite(output)) continue;
    const base = baseModelId(id);
    const prev = card.get(base);
    if (prev && !(near(prev.input, input) && near(prev.output, output))) ambiguous.add(base);
    else card.set(base, { input, output });
  }

  // STATIC_FALLBACK: `"model-id": {"input_per_1k_usd": N, "output_per_1k_usd": N},`
  const block = readFileSync(FALLBACK_TABLE, "utf8").match(/STATIC_FALLBACK\s*=\s*\{([\s\S]*?)\n\}/);
  const rows = [
    ...(block?.[1] ?? "").matchAll(
      /"([^"]+)":\s*\{"input_per_1k_usd":\s*([0-9.eE+-]+),\s*"output_per_1k_usd":\s*([0-9.eE+-]+)\}/g,
    ),
  ];

  if (rows.length === 0) {
    console.log(`pricing drift: NO ROWS PARSED  ${FALLBACK_TABLE} — cannot verify against the rate card`);
    driftCount++;
  }

  let checked = 0;
  for (const [, modelId, inRaw, outRaw] of rows) {
    const base = baseModelId(modelId);
    if (ambiguous.has(base)) {
      console.log(`pricing drift: ambiguous  ${modelId} — rate card lists conflicting rates for ${base}, skipped`);
      continue;
    }
    const expected = card.get(base);
    if (!expected) {
      console.log(`pricing drift: UNVERIFIED  ${modelId} — no row for ${base} in ${RATE_CARD}`);
      driftCount++;
      continue;
    }
    checked++;
    const wantIn = expected.input / 1000;
    const wantOut = expected.output / 1000;
    if (!near(Number(inRaw), wantIn) || !near(Number(outRaw), wantOut)) {
      console.log(
        `pricing drift: MISMATCH  ${modelId} — STATIC_FALLBACK has ${inRaw}/${outRaw} per 1K, ` +
          `rate card says ${expected.input}/${expected.output} per 1M (= ${wantIn}/${wantOut} per 1K)`,
      );
      driftCount++;
    }
  }

  if (driftCount === 0) console.log(`pricing drift: OK (${checked} STATIC_FALLBACK row(s) match the rate card)`);
  else console.log(`pricing drift: ${driftCount} row(s) mismatched or unverified against ${RATE_CARD}`);
}

if (strict && (staleCount > 0 || driftCount > 0)) process.exit(1);
