#!/usr/bin/env python3
"""Assert a Discover run's output against expected-discovery.json.

Usage:
    python3 check_expected_discovery.py <migration_run_dir>

Where <migration_run_dir> contains discovery.json, coupling-score.json, and
preflight-findings.json produced by a replay of this fixture (see README.md).
Exits 0 on PASS, 1 on FAIL with one line per failed assertion. Stdlib only.
(Same pattern as the heroku/gcp live-capture asserters.)
"""

import json
import sys
from pathlib import Path

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILS.append(msg)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    run_dir = Path(sys.argv[1])
    fixture_dir = Path(__file__).resolve().parent
    exp = json.loads((fixture_dir / "expected-discovery.json").read_text())

    docs = {}
    for name in exp["artifacts_must_exist"]:
        p = run_dir / name
        if not p.exists():
            check(False, f"missing artifact {name}")
            continue
        docs[name] = json.loads(p.read_text())
    if "discovery.json" not in docs:
        print(f"FAIL ({len(FAILS)}):")
        for f in FAILS:
            print(f"  - {f}")
        return 1

    disc = docs["discovery.json"]
    disc_text = json.dumps(disc)

    # Route dispositions
    rd = {r["route"]: r for r in disc.get("route_disposition", [])}
    for route, want in exp["route_dispositions"].items():
        r = rd.get(route)
        if r is None:
            check(False, f"route {route} missing from route_disposition")
            continue
        check(r.get("disposition") == want, f"route {route} disposition={r.get('disposition')} want {want}")
    api_route = rd.get("/api/checkout")
    if api_route is not None:
        check(api_route.get("confidence") == "LOW", "/api/checkout must be LOW confidence (manifest sources don't classify Route Handlers)")

    # Manifest metadata
    mm = disc.get("manifest_metadata", {})
    check(mm.get("adapter_api_used") is False, "manifest_metadata.adapter_api_used must be false")

    # Env var names: exact, names only
    check(sorted(disc.get("env_var_names", [])) == sorted(exp["env_var_names_exact"]), f"env_var_names mismatch: {sorted(disc.get('env_var_names', []))}")

    # Storage integrations / peripherals
    stores = disc.get("storage_integrations", [])
    check(len(stores) >= exp["storage_integrations_min"], f"storage_integrations count {len(stores)}")
    ptypes = {p.get("type") for p in disc.get("peripherals", [])} | {s.get("type") for s in stores}
    for t in exp["peripheral_types_must_include"]:
        check(t in ptypes, f"peripheral type {t} missing")

    # Domains
    domains = json.dumps(disc.get("domains", []))
    for d in exp["domains_must_include"]:
        check(d in domains, f"domain {d} missing")

    # Probe absent
    check(not disc.get("header_probe_results"), "header_probe_results must be absent/empty (probe.attempted false)")

    # Pre-flight checks: all 10, unconditional
    pf = docs.get("preflight-findings.json", {})
    pf_text = json.dumps(pf)
    for c in exp["preflight_checks_all_10"]:
        check(f'"{c}"' in pf_text, f"pre-flight check {c} missing")

    # Confidence rules across discovery + preflight findings
    def walk_findings(node, path="$"):
        if isinstance(node, dict):
            if "confidence" in node:
                check(node["confidence"] in exp["confidence_rules"]["every_finding_has_confidence"], f"bad confidence at {path}")
                if node["confidence"] != "HIGH" and exp["confidence_rules"]["non_high_findings_have_upgrade_input"]:
                    check("upgrade_input" in node, f"non-HIGH finding missing upgrade_input at {path}")
            for k, v in node.items():
                walk_findings(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk_findings(v, f"{path}[{i}]")

    walk_findings(disc, "discovery")
    walk_findings(pf, "preflight")

    # Secret hygiene
    all_text = disc_text + pf_text + json.dumps(docs.get("coupling-score.json", {}))
    for bad in ("VERCEL_TOKEN", "Bearer ", "vcp_", "sk_live"):
        check(bad not in all_text, f"possible token/secret material: {bad}")

    def walk_env(node, path="$"):
        if isinstance(node, dict):
            if "name" in node and ("value" in node or "valueFrom" in node):
                check(False, f"env-like object with a value payload at {path}")
            for k, v in node.items():
                walk_env(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk_env(v, f"{path}[{i}]")

    walk_env(disc)
    for key_name in ("STRIPE_SECRET_KEY", "DATABASE_URL"):
        check(f'"{key_name}": ' not in disc_text, f"env name {key_name} appears as a KEY (value paired) — names must be list items only")

    if FAILS:
        print(f"FAIL ({len(FAILS)}):")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("PASS — expected-discovery.json assertions hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
