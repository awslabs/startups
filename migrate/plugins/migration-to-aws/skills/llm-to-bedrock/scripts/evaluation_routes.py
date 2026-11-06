"""Assign golden cases to exact Bedrock workload routes."""

SUPPORTED_PATHS = {
    "runtime_openai_responses", "runtime_openai_chat", "runtime_messages",
    "mantle_openai_responses", "mantle_openai_chat", "mantle_messages",
    "runtime_converse", "runtime_invoke",
}
_IAM_FEATURES = {
    "web_search", "external_web_access", "response_get", "response_cancel",
    "response_delete",
}
_ROUTE_FIELDS = (
    "workload_id", "source_provider", "source_model", "aws_model_id", "migration_path",
    "model_change", "iam_features", "call_sites",
)


def _validate_routes(routes: list[dict]) -> None:
    workload_ids = []
    for route in routes:
        missing = [field for field in _ROUTE_FIELDS if field not in route]
        if missing:
            raise ValueError(f"route missing required field: {missing[0]}")
        if route["migration_path"] not in SUPPORTED_PATHS:
            raise ValueError(f"unknown Bedrock API path: {route['migration_path']}")
        if not route["workload_id"]:
            raise ValueError("route workload_id must be non-empty")
        if not isinstance(route["model_change"], bool):
            raise ValueError("route model_change must be boolean")
        if not isinstance(route["iam_features"], list):
            raise ValueError("route iam_features must be an array")
        unknown_features = set(route["iam_features"]) - _IAM_FEATURES
        if unknown_features:
            raise ValueError(f"unknown IAM route feature: {sorted(unknown_features)[0]}")
        if "external_web_access" in route["iam_features"] and "web_search" not in route["iam_features"]:
            raise ValueError("external_web_access requires web_search on the same route")
        if "web_search" in route["iam_features"] and route["migration_path"] != "mantle_openai_responses":
            raise ValueError(
                "web_search and external_web_access require mantle_openai_responses")
        if not isinstance(route["call_sites"], list):
            raise ValueError("route call_sites must be an array")
        workload_ids.append(route["workload_id"])
    if len(workload_ids) != len(set(workload_ids)):
        raise ValueError("workload route IDs must be unique")


def assign_case_routes(cases: list[dict], routes: list[dict]) -> list[dict]:
    """Return cases enriched with one exact route, or fail on ambiguity."""
    _validate_routes(routes)
    assigned = []
    for case in cases:
        workload_id = case.get("workload_id")
        call_site = case.get("call_site")
        matches = [
            route for route in routes
            if (workload_id and route["workload_id"] == workload_id)
            or (call_site and call_site in route.get("call_sites", []))
        ]
        unique = {route["workload_id"]: route for route in matches}
        if len(unique) != 1:
            identity = workload_id or call_site or case.get("id", "<unknown>")
            raise ValueError(f"Unsupported or ambiguous call-site route: {identity}")
        route = next(iter(unique.values()))
        if workload_id and workload_id != route["workload_id"]:
            raise ValueError(f"Unsupported or ambiguous call-site route: {workload_id}")
        if call_site and call_site not in route["call_sites"]:
            raise ValueError(f"Unsupported or ambiguous call-site route: {call_site}")
        for field in ("aws_model_id", "migration_path", "model_change"):
            if field in case and case[field] != route[field]:
                raise ValueError(f"route attribution changed for case {case.get('id', '<unknown>')}: {field}")
        row = dict(case)
        row.update({field: route[field] for field in _ROUTE_FIELDS})
        row["call_site"] = call_site or (route["call_sites"][0] if route["call_sites"] else "")
        assigned.append(row)
    return assigned


def dispatch_cases(cases: list[dict], routes: list[dict], invokers: dict) -> list:
    """Invoke every case through the callback for its assigned exact path."""
    results = []
    for case in assign_case_routes(cases, routes):
        path = case["migration_path"]
        if path not in invokers:
            raise ValueError(f"no evaluator for Bedrock API path: {path}")
        results.append(invokers[path](case))
    return results
