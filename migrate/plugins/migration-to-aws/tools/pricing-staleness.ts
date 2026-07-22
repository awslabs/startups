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
  if (strict) process.exit(1);
} else {
  console.log(`pricing staleness: OK (${caches.length} cache(s) fresh)`);
}
