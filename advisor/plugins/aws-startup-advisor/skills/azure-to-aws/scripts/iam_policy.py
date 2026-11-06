#!/usr/bin/env python3
"""Generate least-privilege IAM for standalone migration artifacts."""
import argparse
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
_FEATURES = {
    "web_search", "external_web_access", "response_get", "response_cancel",
    "response_delete",
}
_RESPONSE_ACTIONS = {
    "response_get": "bedrock:GetInvoke",
    "response_cancel": "bedrock:CancelInvoke",
    "response_delete": "bedrock:DeleteInvoke",
}


def _foundation_arn(model_id):
    return f"arn:aws:bedrock:*::foundation-model/{model_id}"


def _profile_arn(model_id, region, account_id):
    return f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{model_id}"


def generate_policy(model_ids, region, account_id, api_paths, route_features):
    """Build policy statements from aligned standalone-generation routes."""
    if not (len(model_ids) == len(api_paths) == len(route_features)):
        raise ValueError("model, API path, and feature counts must match")
    routes = []
    for model_id, path, features in zip(model_ids, api_paths, route_features):
        if path not in _RUNTIME_PATHS | _MANTLE_PATHS:
            raise ValueError(f"unknown Bedrock API path: {path}")
        flags = set(features)
        unknown = flags - _FEATURES
        if unknown:
            raise ValueError(f"unknown IAM route feature: {sorted(unknown)[0]}")
        if "external_web_access" in flags and "web_search" not in flags:
            raise ValueError("external_web_access requires web_search on the same route")
        if "web_search" in flags and path != "mantle_openai_responses":
            raise ValueError("web_search and external_web_access require mantle_openai_responses")
        if flags & set(_RESPONSE_ACTIONS) and path != "runtime_openai_responses":
            raise ValueError("stored-response IAM features require runtime_openai_responses")
        routes.append((model_id, path, flags))

    statements = []
    runtime_ids = [model_id for model_id, path, _ in routes if path in _RUNTIME_PATHS]
    resources = []
    for model_id in sorted(set(runtime_ids)):
        if _GEO_PREFIX.match(model_id):
            resources.extend([
                _profile_arn(model_id, region, account_id),
                _foundation_arn(_GEO_PREFIX.sub("", model_id)),
            ])
        else:
            resources.append(_foundation_arn(model_id))
    if runtime_ids:
        statements.append({
            "Sid": "BedrockInvokeModelScoped", "Effect": "Allow",
            "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            "Resource": sorted(set(resources)),
        })
    profiles = sorted({_profile_arn(model_id, region, account_id)
                       for model_id in runtime_ids if _GEO_PREFIX.match(model_id)})
    if profiles:
        statements.append({"Sid": "BedrockGetInferenceProfile", "Effect": "Allow",
                           "Action": ["bedrock:GetInferenceProfile"], "Resource": profiles})
    responses = [flags for _, path, flags in routes if path == "runtime_openai_responses"]
    if responses:
        project = f"arn:aws:bedrock:{region}:{account_id}:project/default"
        statements.append({"Sid": "BedrockResponsesDefaultProject", "Effect": "Allow",
                           "Action": ["bedrock:InvokeModel"], "Resource": project})
        actions = sorted({_RESPONSE_ACTIONS[feature] for flags in responses
                          for feature in flags if feature in _RESPONSE_ACTIONS})
        if actions:
            statements.append({"Sid": "BedrockStoredResponses", "Effect": "Allow",
                               "Action": actions, "Resource": project})
    if any(path in _MANTLE_PATHS for _, path, _ in routes):
        project = f"arn:aws:bedrock-mantle:{region}:{account_id}:project/*"
        statements.extend([
            {"Sid": "BedrockMantleInference", "Effect": "Allow",
             "Action": ["bedrock-mantle:CreateInference", "bedrock-mantle:GetProject",
                        "bedrock-mantle:ListProjects"], "Resource": project},
            {"Sid": "BedrockMantleCallWithBearerToken", "Effect": "Allow",
             "Action": ["bedrock-mantle:CallWithBearerToken"], "Resource": "*"},
        ])
    web = set().union(*(flags for _, _, flags in routes)) if routes else set()
    if "web_search" in web:
        actions = ["bedrock-websearch:InvokeSearch", "bedrock-websearch:InvokeFetch"]
        if "external_web_access" in web:
            actions.append("bedrock-websearch:ExternalWebAccess")
        statements.append({"Sid": "BedrockWebSearch", "Effect": "Allow",
                           "Action": actions, "Resource": "*",
                           "Condition": {"StringEquals": {"aws:RequestedRegion": region}}})
    return {"Version": "2012-10-17", "Statement": statements}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", required=True)
    parser.add_argument("--api-path", required=True)
    parser.add_argument("--features-json", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    models = [value.strip() for value in args.models.split(",") if value.strip()]
    paths = [value.strip() for value in args.api_path.split(",") if value.strip()]
    try:
        features = json.loads(args.features_json)
        policy = generate_policy(models, args.region, args.account_id, paths, features)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    output = json.dumps(policy, indent=2) + "\n"
    if args.output:
        with open(args.output, "w") as stream:
            stream.write(output)
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
