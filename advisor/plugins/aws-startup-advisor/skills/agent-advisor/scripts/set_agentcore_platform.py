"""Set a POC microVM platform and verify it without discarding runtime configuration.

Run only from an authorized deploy step. Requires boto3 at execution time.
API fields: AWS UpdateAgentRuntime/GetAgentRuntime, checked 2026-09-21.
"""
import argparse
import json
import time


UPDATE_FIELDS = (
    "agentRuntimeArtifact", "roleArn", "networkConfiguration", "description",
    "authorizerConfiguration", "requestHeaderConfiguration", "protocolConfiguration",
    "lifecycleConfiguration", "environmentVariables", "filesystemConfigurations",
    "metadataConfiguration",
)


def check_sdk():
    """Check locally before provisioning; this does not resolve AWS credentials."""
    from botocore.session import get_session

    model = get_session().get_service_model("bedrock-agentcore-control")
    update = model.operation_model("UpdateAgentRuntime").input_shape.members
    readback = model.operation_model("GetAgentRuntime").output_shape.members
    if "platformVersion" not in update or "platformVersion" not in readback:
        raise RuntimeError("Upgrade boto3/botocore: platformVersion support is required.")


def wait_ready(client, runtime_id, deadline, expected_revision=None):
    while time.monotonic() < deadline:
        runtime = client.get_agent_runtime(agentRuntimeId=runtime_id)
        status = runtime["status"]
        if status == "READY":
            if expected_revision is None or runtime["agentRuntimeVersion"] == expected_revision:
                return runtime
        elif status not in ("CREATING", "UPDATING"):
            raise RuntimeError(f"Runtime did not become ready: {status}. No fallback was attempted.")
        time.sleep(5)
    raise TimeoutError("Runtime readiness timed out. Inspect its status before updating or deleting.")


def set_platform(client, runtime_id, version):
    if version not in ("V1", "V2"):
        raise ValueError("Platform must be V1 or V2.")
    deadline = time.monotonic() + 900
    runtime = wait_ready(client, runtime_id, deadline)
    if runtime.get("capacityProviderConfiguration"):
        raise ValueError("Platform selection applies to microVMs, not Instances.")
    if runtime.get("platformVersion") not in ("V1", "V2"):
        raise RuntimeError("GetAgentRuntime did not return a recognized platformVersion.")
    if runtime["platformVersion"] != version:
        params = {key: runtime[key] for key in UPDATE_FIELDS if key in runtime}
        params.update(agentRuntimeId=runtime_id, platformVersion=version)
        response = client.update_agent_runtime(**params)
        runtime = wait_ready(
            client, runtime_id, time.monotonic() + 900, response["agentRuntimeVersion"]
        )
    if runtime["platformVersion"] != version:
        raise RuntimeError("Deployed platform does not match the recommendation.")
    return {key: runtime[key] for key in (
        "agentRuntimeId", "agentRuntimeVersion", "platformVersion", "status"
    )}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-sdk", action="store_true")
    parser.add_argument("--runtime-id")
    parser.add_argument("--region")
    parser.add_argument("--platform-version", choices=("V1", "V2"))
    args = parser.parse_args()
    check_sdk()
    if args.check_sdk:
        return
    if not all((args.runtime_id, args.region, args.platform_version)):
        parser.error("--runtime-id, --region, and --platform-version are required")
    import boto3

    client = boto3.client("bedrock-agentcore-control", region_name=args.region)
    print(json.dumps(set_platform(client, args.runtime_id, args.platform_version)))


if __name__ == "__main__":
    main()
