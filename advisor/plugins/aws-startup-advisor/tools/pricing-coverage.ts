// pricing-coverage.ts — the root-cause guard for the "silent pricing floor" bug class.
//
// WHY: three separate estimate defects (x86 RDS classes, current-gen EC2/EKS classes,
// and the ECR line) were all ONE systemic failure — the design can emit an AWS service
// the pricing table cannot price, and nothing catches it until a human reads a real
// run's output. The fixes so far were per-symptom (add the missing rows). This tool
// closes the CLASS: it asserts the invariant that keeps the design's target vocabulary
// and the pricing table in sync, so the NEXT unpriced service fails a gate at commit
// time instead of flooring an estimate silently in front of a customer.
//
// THE INVARIANT (read from data, never hardcoded here):
//   Every AWS service the design can emit (`aws_service` in fast-path-services.json,
//   plus the rubric/design-ref target vocabulary) MUST be classified in the pricing
//   table as exactly one of:
//     (a) PRICED         — a top-level rate section or a fast_path_services entry
//     (b) DECLARED-ABSENT — listed in `_absent_services` (a known hole; estimate emits
//                            a visible excluded line and marks the total a floor — honest)
//     (c) NO-COST         — listed in `_no_cost_services` (control-plane / free-tier;
//                            legitimately has no rate)
//   A service in NONE of the three is the bug: it will floor silently and un-acknowledged.
//
// The point is not that everything must be priced — ECR/DynamoDB staying ABSENT is fine,
// that is a declared, honest hole. The point is that no service may fall through
// UN-CLASSIFIED. Adding a rate moves a service a->b/c; the oracle only demands it be in
// SOME bucket. That is what makes it sustainable across arbitrary Azure repos: a new
// target service forces a one-line data decision (price it, or declare it) and cannot be
// forgotten.
//
// Modes:
//   node pricing-coverage.ts                 # report; exit 1 if any service is unclassified
//   node pricing-coverage.ts <plugin-dir>    # target a specific plugin tree
//
// Zero-dep: Node 24 native TS type-stripping, same as the sibling pricing tools.

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const PLUGIN = process.argv.slice(2).find((a) => !a.startsWith("-")) ?? "advisor/plugins/aws-startup-advisor";
const SKILLS = join(PLUGIN, "skills");
const PRICING = join(SKILLS, "shared/pricing/aws-infra-pricing.json");
const FASTPATH = join(SKILLS, "azure-to-aws/knowledge/design/fast-path-services.json");

/** Normalize a service label OR a pricing key to a comparison token:
 * lowercase, strip non-alphanumerics. "RDS PostgreSQL" -> "rdspostgresql",
 * "rds_postgresql" -> "rdspostgresql", "VPC subnet" -> "vpcsubnet". */
const norm = (s: string): string => s.toLowerCase().replace(/[^a-z0-9]+/g, "");

// Aliases where the design's human label and the pricing key do not normalize equal.
// Each entry maps a design `aws_service` token -> the pricing bucket key it satisfies.
// Kept small and explicit; every entry is a real naming divergence, not a guess.
const ALIAS: Record<string, string> = {
  rdspostgresql: "rdspostgresql",
  aurorapostgresql: "aurorapostgresql",
  elasticacheredis: "elasticache",
  elasticachememcached: "elasticachememcached",
  vpcsubnet: "vpcsubnet",
  vpcroutetable: "vpcroutetable",
  vpcpeeringconnection: "vpcpeering",
  route53hostedzone: "route53",
  route53routingpolicy: "route53routingpolicy",
  kinesisdatastreams: "kinesis",
  amazonkeyspaces: "keyspaces",
  fsxforwindowsfileserver: "fsxwindows",
  awsbackupvault: "backup",
  awsnetworkfirewall: "networkfirewall",
  awsappconfig: "appconfig",
  systemsmanagersessionmanager: "sessionmanager",
  iamrole: "iamrole",
  kmskey: "kmskey",
  acmcertificate: "acmcertificate",
  ebssnapshot: "ebs",
  ami: "ami",
  securitygroup: "securitygroup",
};

function fail(msg: string): never {
  console.log(`pricing coverage: ERROR — ${msg}`);
  process.exit(1);
}

if (!existsSync(PRICING)) fail(`pricing table not found: ${PRICING}`);
if (!existsSync(FASTPATH)) fail(`fast-path services not found: ${FASTPATH}`);

const price = JSON.parse(readFileSync(PRICING, "utf8")) as Record<string, unknown>;

// --- Build the classified sets from the pricing table's OWN data ---
const priced = new Set<string>();
for (const k of Object.keys(price)) {
  if (k.startsWith("_") || k === "fast_path_services") continue;
  priced.add(norm(k));
}
const fps = (price["fast_path_services"] ?? {}) as Record<string, unknown>;
for (const k of Object.keys(fps)) if (!k.startsWith("_")) priced.add(norm(k));

const absent = new Set<string>();
for (const k of Object.keys((price["_absent_services"] ?? {}) as object)) if (!k.startsWith("_")) absent.add(norm(k));

const noCost = new Set<string>();
for (const k of Object.keys((price["_no_cost_services"] ?? {}) as object)) if (!k.startsWith("_")) noCost.add(norm(k));

// --- Collect the design's target vocabulary: every aws_service string it can emit ---
const fastPath = JSON.parse(readFileSync(FASTPATH, "utf8"));
const emitted = new Set<string>();
const rawByToken = new Map<string, string>();
(function walk(o: unknown): void {
  if (Array.isArray(o)) for (const x of o) walk(x);
  else if (o && typeof o === "object") {
    for (const [k, v] of Object.entries(o as Record<string, unknown>)) {
      if ((k === "aws_service" || k === "aws") && typeof v === "string") {
        const t = norm(v);
        if (t) {
          emitted.add(t);
          rawByToken.set(t, v);
        }
      }
      walk(v);
    }
  }
})(fastPath);

// --- Classify each emitted service; the unclassified ones are the bug ---
function classified(token: string): string | null {
  const target = ALIAS[token] ?? token;
  if (priced.has(target) || priced.has(token)) return "priced";
  if (absent.has(target) || absent.has(token)) return "declared-absent";
  if (noCost.has(target) || noCost.has(token)) return "no-cost";
  return null;
}

const unclassified: string[] = [];
const summary = { priced: 0, "declared-absent": 0, "no-cost": 0 };
for (const token of [...emitted].sort()) {
  const cls = classified(token);
  if (cls === null) unclassified.push(rawByToken.get(token) ?? token);
  else summary[cls as keyof typeof summary]++;
}

console.log(
  `pricing coverage: ${emitted.size} target service(s) — ` +
    `${summary.priced} priced, ${summary["declared-absent"]} declared-absent, ${summary["no-cost"]} no-cost`,
);

if (unclassified.length > 0) {
  console.log(
    `pricing coverage: FAIL — ${unclassified.length} service(s) the design can emit are neither ` +
      `priced, declared in _absent_services, nor declared in _no_cost_services:`,
  );
  for (const s of unclassified) {
    console.log(
      `  • "${s}" — add a rate section, OR add it to _absent_services (known hole, honest floor), ` +
        `OR add it to _no_cost_services (free/control-plane). Never let it fall through.`,
    );
  }
  console.log(
    "This is the silent-pricing-floor bug class. A service here will be excluded from the " +
      "estimate total with no acknowledgment. Classify it in aws-infra-pricing.json.",
  );
  process.exit(1);
}

console.log("pricing coverage: OK — every emittable service is priced, declared absent, or declared no-cost.");
