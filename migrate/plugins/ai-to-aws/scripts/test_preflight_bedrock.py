# test_preflight_bedrock.py
import preflight_bedrock as p


def test_classify_access_denied_maps_to_authz_failure():
    # The pure classifier turns a botocore error code into a structured verdict.
    v = p.classify_invoke_error("AccessDeniedException", "not authorized to perform bedrock:InvokeModel")
    assert v["ok"] is False
    assert v["reason"] == "authz"
    assert "bedrock:InvokeModel" in v["detail"]


def test_classify_model_not_available_suggests_cross_region_profile():
    v = p.classify_invoke_error("ValidationException", "model identifier is invalid")
    assert v["ok"] is False
    assert v["reason"] == "model_unavailable"


def test_classify_throttle_is_ok_for_preflight():
    # A throttle on the 1-token probe means we ARE authorized — treat as pass.
    v = p.classify_invoke_error("ThrottlingException", "rate exceeded")
    assert v["ok"] is True


def test_classify_expired_token_maps_to_credentials():
    v = p.classify_invoke_error("ExpiredTokenException", "The security token included in the request is expired")
    assert v["ok"] is False
    assert v["reason"] == "credentials"


def test_probe_model_botocore_error_returns_json_verdict_not_traceback():
    # Regression: NoCredentialsError used to escape as an unhandled traceback,
    # so the orchestrator's JSON parse failed exactly when guidance was needed.
    from botocore.exceptions import NoCredentialsError

    class NoCredsClient:
        def converse(self, **kwargs):
            raise NoCredentialsError()

    v = p.probe_model(NoCredsClient(), "any.model-v1:0")
    assert v["ok"] is False
    assert v["reason"] == "credentials"
    assert "NoCredentialsError" in v["detail"]


def test_quota_rpm_matches_model_name_token():
    quotas = [
        {"QuotaName": "On-demand model inference requests per minute for Anthropic Claude Haiku 4.5", "Value": 50.0},
        {"QuotaName": "On-demand model inference requests per minute for Amazon Nova Lite", "Value": 1000.0},
        {"QuotaName": "Cross-region model inference tokens per day for Anthropic Claude", "Value": 9.9e9},
    ]
    rpm = p.quota_rpm(quotas, "us.anthropic.claude-haiku-4-5-20251001-v1:0")
    assert rpm == 50  # the Nova quota and the per-day quota must not match


def test_quota_rpm_no_match_returns_none():
    quotas = [{"QuotaName": "On-demand model inference requests per minute for Amazon Nova Lite", "Value": 1000.0}]
    assert p.quota_rpm(quotas, "us.anthropic.claude-haiku-4-5-20251001-v1:0") is None


def test_main_empty_models_is_a_failure_not_a_vacuous_pass(capsys):
    # Regression: `--models ""` used to exit 0 with all_ok=True.
    import json
    rc = p.main(["--region", "us-east-1", "--models", " , "])
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert out["reason"] == "no_models"


def test_embedding_model_detection():
    assert p.is_embedding_model("amazon.titan-embed-text-v2:0") is True
    assert p.is_embedding_model("cohere.embed-english-v3") is True
    assert p.is_embedding_model("us.anthropic.claude-haiku-4-5-20251001-v1:0") is False


def test_probe_routes_embedding_models_to_invoke_model_not_converse():
    # Regression: titan-embed probed via converse() got ValidationException and
    # was misreported as model_unavailable, blocking valid embeddings migrations.
    class Recorder:
        called = None
        def converse(self, **kwargs):
            Recorder.called = "converse"
            return {}
        def invoke_model(self, **kwargs):
            Recorder.called = "invoke_model"
            assert kwargs["modelId"] == "amazon.titan-embed-text-v2:0"
            import json as j
            assert "inputText" in j.loads(kwargs["body"])
            return {}

    v = p.probe_model(Recorder(), "amazon.titan-embed-text-v2:0")
    assert Recorder.called == "invoke_model"
    assert v["ok"] is True


def test_probe_unknown_embedding_family_passes_with_caveat():
    class Boom:
        def converse(self, **kwargs):
            raise AssertionError("must not call converse for embeddings")
        def invoke_model(self, **kwargs):
            raise AssertionError("must not probe an unknown embedding family")

    v = p.probe_model(Boom(), "somevendor.embed-x-v1:0")
    assert v["ok"] is True
    assert v["reason"] == "embedding_unprobed"


def test_aggregate_failure_lifts_first_failing_reason_to_top_level():
    # Regression: per-model failures left no top-level reason, so the
    # orchestrator's documented `ok==false + reason` branches never matched.
    results = [
        {"ok": True, "reason": "ok", "detail": "fine", "model_id": "m1"},
        {"ok": False, "reason": "model_unavailable", "detail": "nope", "model_id": "m2"},
        {"ok": False, "reason": "authz", "detail": "denied", "model_id": "m3"},
    ]
    agg = p.aggregate_failure(results)
    assert agg["reason"] == "model_unavailable"
    assert agg["failing_models"] == ["m2", "m3"]


def test_aggregate_failure_empty_when_all_ok():
    assert p.aggregate_failure([{"ok": True, "reason": "ok", "detail": "", "model_id": "m"}]) == {}


def test_access_denied_model_access_variant_routes_to_console_fix():
    # Bedrock's "model access not enabled" also surfaces as AccessDeniedException;
    # sending the user to IAM for it is the wrong fix.
    v = p.classify_invoke_error(
        "AccessDeniedException",
        "You don't have access to the model with the specified model ID. "
        "Enable model access in the Amazon Bedrock console.")
    assert v["ok"] is False
    assert v["reason"] == "model_access"
    assert "console" in v["detail"].lower()


def test_access_denied_iam_variant_still_routes_to_authz():
    v = p.classify_invoke_error(
        "AccessDeniedException",
        "User: arn:aws:iam::123:user/x is not authorized to perform: "
        "bedrock:InvokeModel on resource ...")
    assert v["reason"] == "authz"
    assert "bedrock:InvokeModel" in v["detail"]
