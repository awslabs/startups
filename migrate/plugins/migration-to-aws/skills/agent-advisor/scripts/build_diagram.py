"""Deterministic architecture-diagram composer for agent-advisor.

Pure: (scoring-result, confirm) dicts -> {"mermaid": str, "ascii": str}.
Same input -> byte-identical output. No timestamps, no randomness.
"""
import json
import pathlib

RUNTIME_LABELS = {
    "agentcore": "AgentCore Runtime",
    "lambda_microvms": "Lambda MicroVMs",
    "ecs": "Amazon ECS (Fargate)",
    "eks": "Amazon EKS",
    "lambda": "AWS Lambda",
    "none": "No viable runtime",
}

SERVICE_LABELS = {
    "identity": "Identity",
    "observability": "Observability",
    "evaluations": "Evaluations",
    "optimization": "Optimization",
    "memory": "Memory",
    "gateway": "Gateway",
    "policy": "Policy",
    "managed_kb": "Managed KB",
    "code_interpreter": "Code Interpreter",
    "browser": "Browser",
    "web_search": "Web Search",
    "sandbox": "Sandbox",
    "payments": "Payments",
    "registry": "Registry",
}

# Runtimes whose compute layer needs heavy infrastructure execution (clusters,
# Terraform) handed off to migration-to-aws. AgentCore, Lambda MicroVMs, and
# standard Lambda are self-contained deliverables from this advisor — not handoffs.
HANDOFF_RUNTIMES = {"ecs", "eks"}


def resolve_runtime(result, confirm):
    verdict = result.get("verdict")
    if verdict == "co_recommend":
        return confirm.get("chosen_runtime") or result.get("co_recommend", ["none"])[0]
    if verdict == "no_viable_runtime":
        return "none"
    return verdict


def resolve_services(result, confirm):
    services = confirm.get("agentcore_services") or result.get("agentcore_services", [])
    seen, out = set(), []
    for sid in services:
        if sid in SERVICE_LABELS and sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


def render_mermaid(runtime, services, model, deployment_model):
    label = RUNTIME_LABELS.get(runtime, runtime)
    if runtime == "agentcore" and deployment_model:
        label = f"{label}<br/>({deployment_model})"
    lines = ["flowchart TD"]
    # Primary request/data flow (solid): user invokes the runtime, runtime calls the model.
    lines.append(f'    user["User / Client"]')
    lines.append(f'    rt["{label}"]')
    lines.append(f'    model["Bedrock model:<br/>{model}"]')
    lines.append("    user -->|request| rt")
    lines.append("    rt -->|invoke| model")
    # AgentCore services are cross-cutting capabilities attached to the runtime, NOT
    # downstream call targets — group them in a subgraph and attach with dotted edges.
    if services:
        lines.append('    subgraph svcs["AgentCore services"]')
        lines.append("        direction LR")
        for sid in services:
            lines.append(f'        svc_{sid}["{SERVICE_LABELS[sid]}"]')
        lines.append("    end")
        lines.append("    rt -.-> svcs")
    if runtime in HANDOFF_RUNTIMES:
        lines.append('    handoff["Compute configured by migration-to-aws"]')
        lines.append("    rt -.-> handoff")
    return "\n".join(lines)


def render_ascii(runtime, services, model, deployment_model):
    label = RUNTIME_LABELS.get(runtime, runtime)
    if runtime == "agentcore" and deployment_model:
        label = f"{label} ({deployment_model})"
    # Primary flow: user -> runtime -> Bedrock model.
    lines = [
        "User / Client",
        "    |  request",
        "    v",
        f"[ {label} ]",
        f"    |  invoke",
        "    v",
        f"Bedrock model: {model}",
    ]
    # Services are attached capabilities, shown separately (not as call targets).
    if services:
        lines.append("")
        lines.append(f"[ {label} ] .. attached AgentCore services:")
        for sid in services:
            lines.append(f"  - {SERVICE_LABELS[sid]}")
    if runtime in HANDOFF_RUNTIMES:
        lines.append("")
        lines.append("Note: compute configured by migration-to-aws")
    return "\n".join(lines)


def build_diagram(result, confirm):
    runtime = resolve_runtime(result, confirm)
    if runtime == "none":
        msg = "No viable runtime — see blocking constraints"
        return {
            "mermaid": f'flowchart TD\n    n["{msg}"]',
            "ascii": f"[ {RUNTIME_LABELS['none']} ]\n{msg}",
        }
    services = resolve_services(result, confirm)
    model = result.get("model_recommendation", {}).get("model", "unknown")
    deployment_model = result.get("deployment_model")
    return {
        "mermaid": render_mermaid(runtime, services, model, deployment_model),
        "ascii": render_ascii(runtime, services, model, deployment_model),
    }


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="agent-advisor diagram composer")
    parser.add_argument("result", type=pathlib.Path)
    parser.add_argument("confirm", type=pathlib.Path)
    args = parser.parse_args(argv)
    result = json.loads(args.result.read_text())
    confirm = json.loads(args.confirm.read_text()) if args.confirm.exists() else {}
    diagram = build_diagram(result, confirm)
    out = (
        "```mermaid\n" + diagram["mermaid"] + "\n```\n\n"
        "<details><summary>ASCII (plain-text fallback)</summary>\n\n"
        "```\n" + diagram["ascii"] + "\n```\n\n</details>\n"
    )
    out_path = args.result.parent / "diagram.md"
    out_path.write_text(out)
    print(f"RESULT=ok RUNTIME={resolve_runtime(result, confirm)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
