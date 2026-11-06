"""Generate least-privilege IAM policy for selected Bedrock API paths."""
import json
import re
import sys

_GEO_PREFIX = re.compile(r"^(us|eu|apac|in|global)\.")
_RUNTIME_PATHS = {
    "runtime_openai_responses", "runtime_openai_chat", "runtime_messages",
    "runtime_converse", "runtime_invoke",
}
_MANTLE_PATHS = {
    "mantle_openai_responses", "mantle_openai_chat", "mantle_messages",
}
_LEGACY_PATHS = {"converse": "runtime_converse", "gpt-oss": "runtime_converse",
                 "mantle": "mantle_openai_responses"}


def is_inference_profile(model_id: str) -> bool:
    return bool(_GEO_PREFIX.match(model_id))


def is_mantle_model(model_id: str) -> bool:
    """Legacy model-family inference used only when no API path is supplied."""
    mid = model_id.lower()
    return mid.startswith("openai.gpt-5") and "oss" not in mid


def mantle_project_arn(region: str, account_id: str) -> str:
    return f"arn:aws:bedrock-mantle:{region}:{account_id}:project/*"


def foundation_model_arn(model_id: str) -> str:
    return f"arn:aws:bedrock:*::foundation-model/{model_id}"


def inference_profile_arn(model_id: str, region: str, account_id: str) -> str:
    return f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{model_id}"


def _normalize_path(path: str | None, model_id: str) -> str:
    if path is None or not path.strip():
        return "mantle_openai_responses" if is_mantle_model(model_id) else "runtime_converse"
    normalized = _LEGACY_PATHS.get(path.strip(), path.strip())
    if normalized not in _RUNTIME_PATHS | _MANTLE_PATHS:
        raise ValueError(f"unknown Bedrock API path: {path}")
    return normalized


def _paths_for_models(model_ids: list[str], api_paths) -> list[str]:
    if api_paths is None:
        supplied = [None] * len(model_ids)
    elif isinstance(api_paths, str):
        values = [value.strip() for value in api_paths.split(",") if value.strip()]
        supplied = values * len(model_ids) if len(values) == 1 else values
    else:
        supplied = list(api_paths)
        if len(supplied) == 1:
            supplied *= len(model_ids)
    if len(supplied) != len(model_ids):
        raise ValueError("API path count must be one or match the model count")
    return [_normalize_path(path, model_id) for model_id, path in zip(model_ids, supplied)]


def generate_policy(model_ids: list[str], region: str, account_id: str,
                    api_paths=None) -> dict:
    """Build policy statements from endpoint intent, retaining legacy inference."""
    paths = _paths_for_models(model_ids, api_paths)
    runtime_ids = [mid for mid, path in zip(model_ids, paths) if path in _RUNTIME_PATHS]
    mantle_ids = [mid for mid, path in zip(model_ids, paths) if path in _MANTLE_PATHS]
    statements = []

    resources = []
    for model_id in sorted(set(runtime_ids)):
        if is_inference_profile(model_id):
            resources.append(inference_profile_arn(model_id, region, account_id))
            resources.append(foundation_model_arn(_GEO_PREFIX.sub("", model_id)))
        else:
            resources.append(foundation_model_arn(model_id))
    if resources or not mantle_ids:
        statements.append({
            "Sid": "BedrockInvokeModelScoped", "Effect": "Allow",
            "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            "Resource": sorted(set(resources)),
        })

    if mantle_ids:
        statements.extend([
            {
                "Sid": "BedrockMantleInference", "Effect": "Allow",
                "Action": ["bedrock-mantle:CreateInference",
                           "bedrock-mantle:GetProject",
                           "bedrock-mantle:ListProjects"],
                "Resource": mantle_project_arn(region, account_id),
            },
            {
                "Sid": "BedrockMantleCallWithBearerToken", "Effect": "Allow",
                "Action": ["bedrock-mantle:CallWithBearerToken"], "Resource": "*",
            },
        ])
    return {"Version": "2012-10-17", "Statement": statements}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate scoped Bedrock IAM policy")
    parser.add_argument("--models", required=True, help="Comma-separated model IDs")
    parser.add_argument("--api-path", help="One selected path, or comma-separated paths aligned to models")
    parser.add_argument("--region", required=True, help="AWS region")
    parser.add_argument("--account-id", required=True, help="AWS account ID")
    parser.add_argument("--output", help="Output file (default: stdout)")
    args = parser.parse_args()
    model_ids = [model.strip() for model in args.models.split(",") if model.strip()]
    try:
        policy = generate_policy(model_ids, args.region, args.account_id, args.api_path)
    except ValueError as exc:
        parser.error(str(exc))
    output = json.dumps(policy, indent=2) + "\n"
    if args.output:
        with open(args.output, "w") as stream:
            stream.write(output)
        print(f"Policy written to {args.output}", file=sys.stderr)
    else:
        print(output)
