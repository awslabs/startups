"""End-to-end contracts for deterministic golden-case route dispatch."""
import pytest

from evaluation_routes import assign_case_routes, dispatch_cases


ROUTES = [
    {
        "workload_id": "wl-responses",
        "source_provider": "openai",
        "source_model": "gpt-5.4",
        "aws_model_id": "global.openai.gpt-5.4",
        "migration_path": "runtime_openai_responses",
        "model_change": False,
        "iam_features": [],
        "call_sites": ["src/app.py:10"],
    },
    {
        "workload_id": "wl-chat",
        "source_provider": "openai",
        "source_model": "gpt-5.4",
        "aws_model_id": "global.openai.gpt-5.4",
        "migration_path": "runtime_openai_chat",
        "model_change": False,
        "iam_features": [],
        "call_sites": ["src/app.py:20"],
    },
]


def test_same_model_responses_and_chat_cases_invoke_assigned_apis():
    cases = [
        {"id": "p1", "workload_id": "wl-responses", "call_site": "src/app.py:10"},
        {"id": "p2", "workload_id": "wl-chat", "call_site": "src/app.py:20"},
    ]
    calls = []

    def invoke(path):
        def call(case):
            calls.append((case["id"], path, case["aws_model_id"]))
            return path
        return call

    results = dispatch_cases(cases, ROUTES, {
        "runtime_openai_responses": invoke("runtime_openai_responses"),
        "runtime_openai_chat": invoke("runtime_openai_chat"),
    })

    assert results == ["runtime_openai_responses", "runtime_openai_chat"]
    assert calls == [
        ("p1", "runtime_openai_responses", "global.openai.gpt-5.4"),
        ("p2", "runtime_openai_chat", "global.openai.gpt-5.4"),
    ]


def test_call_site_can_supply_the_stable_route_identity():
    [case] = assign_case_routes([{"id": "p1", "call_site": "src/app.py:20"}], ROUTES)
    assert case["workload_id"] == "wl-chat"
    assert case["migration_path"] == "runtime_openai_chat"
    assert case["model_change"] is False


def test_unattributed_or_ambiguous_case_fails_closed():
    with pytest.raises(ValueError, match="Unsupported or ambiguous"):
        assign_case_routes([{"id": "missing"}], ROUTES)
    with pytest.raises(ValueError, match="Unsupported or ambiguous"):
        assign_case_routes([
            {"id": "conflict", "workload_id": "wl-responses", "call_site": "src/app.py:20"}
        ], ROUTES)


def test_routes_cannot_be_collapsed_by_shared_model_and_path():
    duplicate_id = [dict(ROUTES[0]), dict(ROUTES[0])]
    with pytest.raises(ValueError, match="route IDs must be unique"):
        assign_case_routes([{"id": "p1", "workload_id": "wl-responses"}], duplicate_id)


def test_runtime_responses_with_web_search_fails_before_invocation():
    route = dict(ROUTES[0], iam_features=["web_search"])
    called = False

    def invoke(case):
        nonlocal called
        called = True

    with pytest.raises(ValueError, match="mantle_openai_responses"):
        dispatch_cases(
            [{"id": "p1", "workload_id": "wl-responses"}], [route],
            {"runtime_openai_responses": invoke},
        )
    assert called is False
