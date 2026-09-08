"""Check the primary recommendation produced by the OpenAI demo scenarios."""

import argparse
import json
import pathlib

EXPECTED = {
    "provider": "openai",
    "decision_status": "recommended",
    "api_path": "mantle_openai_responses",
    "primary_model": "openai.gpt-5.4",
    "probe_status": "not_run",
}

EXPECTED_MODALITY_TARGETS = {"embeddings", "audio_modality"}


def check(path, scenario):
    data = json.loads(pathlib.Path(path).read_text())
    unit = data["primary_unit"] if "primary_unit" in data else data
    workloads = data.get("workloads") or [unit]
    errors = []
    for w in workloads:
        pm = w.get("provider_module") or {}
        if pm.get("decision_status") not in ("recommended", "decision_required"):
            errors.append(f"decision_status={pm.get('decision_status')}")
        if pm.get("api_path") != EXPECTED["api_path"]:
            errors.append(f"api_path={pm.get('api_path')} (want {EXPECTED['api_path']})")
        primary = pm.get("primary_model") or {}
        if primary.get("invocation_model_id") != EXPECTED["primary_model"]:
            errors.append(
                f"primary_model={primary.get('invocation_model_id')} (want {EXPECTED['primary_model']})"
            )
        verification = pm.get("verification") or {}
        if verification.get("probe_status") != EXPECTED["probe_status"]:
            errors.append(f"probe_status={verification.get('probe_status')}")
        targets = pm.get("additional_targets") or []
        for i, t in enumerate(targets):
            if t.get("status") == "unresolved" and t.get("candidate") is None:
                errors.append(f"additional_target[{i}] unresolved with null candidate")
        modalities = {t.get("capability") for t in targets}
        missing = EXPECTED_MODALITY_TARGETS - modalities
        if missing:
            errors.append(f"missing additional targets: {sorted(missing)}")
        prov = (pm.get("catalog_provenance") or {}).get("provider")
        if prov and prov != EXPECTED["provider"]:
            errors.append(f"catalog_provenance.provider={prov}")
    if errors:
        raise SystemExit("FAIL scenario=%s: %s" % (scenario, "; ".join(errors)))
    print("PASS scenario=" + scenario + " workload=" + str(len(workloads)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact")
    parser.add_argument("--scenario", default="openai")
    ns = parser.parse_args()
    check(ns.artifact, ns.scenario)


if __name__ == "__main__":
    main()
