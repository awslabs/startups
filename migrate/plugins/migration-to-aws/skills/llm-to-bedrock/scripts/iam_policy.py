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
_IAM_FEATURES = {
    "web_search", "external_web_access", "response_get", "response_cancel",
    "response_delete",
}
_RESPONSE_ACTIONS = {
    "response_get": "bedrock:GetInvoke",
    "response_cancel": "bedrock:CancelInvoke",
    "response_delete": "bedrock:DeleteInvoke",
}


def is_inference_profile(model_id: str) -> bool:
    return bool(_GEO_PREFIX.match(model_id))


def is_mantle_model(model_id: str) -> bool:
    """Legacy model-family inference used only when no API path is supplied."""
    mid = model_id.lower()
    return mid.startswith("openai.gpt-5") and "oss" not in mid


def mantle_project_arn(region: str, account_id: str) -> str:
    return f"arn:aws:bedrock-mantle:{region}:{account_id}:project/*"


def runtime_default_project_arn(region: str, account_id: str) -> str:
    return f"arn:aws:bedrock:{region}:{account_id}:project/default"


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


def _features_for_models(model_ids: list[str], route_features) -> list[set[str]]:
    if route_features is None:
        supplied = [[] for _ in model_ids]
    elif isinstance(route_features, str):
        try:
            supplied = json.loads(route_features)
        except json.JSONDecodeError as exc:
            raise ValueError("route features must be a JSON array") from exc
        if not isinstance(supplied, list):
            raise ValueError("route features must be a JSON array")
    else:
        supplied = list(route_features)
    if len(supplied) == 1 and len(model_ids) > 1:
        supplied *= len(model_ids)
    if len(supplied) != len(model_ids):
        raise ValueError("route feature count must be one or match the model count")

    normalized = []
    for features in supplied:
        values = [features] if isinstance(features, str) else list(features)
        unknown = set(values) - _IAM_FEATURES
        if unknown:
            raise ValueError(f"unknown IAM route feature: {sorted(unknown)[0]}")
        if "external_web_access" in values and "web_search" not in values:
            raise ValueError("external_web_access requires web_search on the same route")
        normalized.append(set(values))
    return normalized


def generate_policy(model_ids: list[str], region: str, account_id: str,
                    api_paths=None, route_features=None) -> dict:
    """Build policy statements from aligned route intent, retaining legacy inference."""
    paths = _paths_for_models(model_ids, api_paths)
    features = _features_for_models(model_ids, route_features)
    routes = list(zip(model_ids, paths, features))
    response_features = set(_RESPONSE_ACTIONS)
    for _, path, flags in routes:
        if flags & response_features and path != "runtime_openai_responses":
            raise ValueError("stored-response IAM features require runtime_openai_responses")
        if "web_search" in flags and path != "mantle_openai_responses":
            raise ValueError(
                "web_search and external_web_access require mantle_openai_responses")
    runtime_ids = [mid for mid, path, _ in routes if path in _RUNTIME_PATHS]
    mantle_ids = [mid for mid, path, _ in routes if path in _MANTLE_PATHS]
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

    profile_resources = sorted({
        inference_profile_arn(mid, region, account_id)
        for mid in runtime_ids if is_inference_profile(mid)
    })
    if profile_resources:
        statements.append({
            "Sid": "BedrockGetInferenceProfile", "Effect": "Allow",
            "Action": ["bedrock:GetInferenceProfile"],
            "Resource": profile_resources,
        })

    response_routes = [(path, flags) for _, path, flags in routes
                       if path == "runtime_openai_responses"]
    if response_routes:
        project_arn = runtime_default_project_arn(region, account_id)
        statements.append({
            "Sid": "BedrockResponsesDefaultProject", "Effect": "Allow",
            "Action": ["bedrock:InvokeModel"], "Resource": project_arn,
        })
        stored_actions = sorted({
            action for _, flags in response_routes
            for feature, action in _RESPONSE_ACTIONS.items() if feature in flags
        })
        if stored_actions:
            statements.append({
                "Sid": "BedrockStoredResponses", "Effect": "Allow",
                "Action": stored_actions, "Resource": project_arn,
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

    web_features = set().union(*(flags for _, _, flags in routes)) if routes else set()
    if "web_search" in web_features:
        actions = ["bedrock-websearch:InvokeSearch", "bedrock-websearch:InvokeFetch"]
        if "external_web_access" in web_features:
            actions.append("bedrock-websearch:ExternalWebAccess")
        statements.append({
            "Sid": "BedrockWebSearch", "Effect": "Allow", "Action": actions,
            "Resource": "*",
            "Condition": {"StringEquals": {"aws:RequestedRegion": region}},
        })
    return {"Version": "2012-10-17", "Statement": statements}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate scoped Bedrock IAM policy")
    parser.add_argument("--models", required=True, help="Comma-separated model IDs")
    parser.add_argument("--api-path", help="One selected path, or comma-separated paths aligned to models")
    parser.add_argument("--features-json", help="JSON array of IAM feature arrays aligned to models")
    parser.add_argument("--region", required=True, help="AWS region")
    parser.add_argument("--account-id", required=True, help="AWS account ID")
    parser.add_argument("--output", help="Output file (default: stdout)")
    args = parser.parse_args()
    model_ids = [model.strip() for model in args.models.split(",") if model.strip()]
    try:
        policy = generate_policy(
            model_ids, args.region, args.account_id, args.api_path, args.features_json)
    except ValueError as exc:
        parser.error(str(exc))
    output = json.dumps(policy, indent=2) + "\n"
    if args.output:
        with open(args.output, "w") as stream:
            stream.write(output)
        print(f"Policy written to {args.output}", file=sys.stderr)
    else:
        print(output)
