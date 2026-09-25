# AgentCore microVM platform version

Load in Design after resolving each unit's `effective_runtime`, and again before generating
an AgentCore POC. This policy does not change runtime scores or compute-type routing.

## Default and exceptions

For `effective_runtime == "agentcore"` with `agentcore_compute_type == "microvms"`,
recommend **V2 by default**. Do not add a V1/V2 preference question. The service's default is
still V1: the deploy artifact must explicitly select the recommended platform.
Platform versions are separate from the numeric agent runtime revisions.

Check the target Region, source/deployment type, environment variables, initialization code,
and deployment tooling using the current run's evidence. New code should be written for V2.
For existing code, identify the specific changes needed for snapshot restore before deployment.
Repair straightforward incompatibilities within the authorized implementation scope.

Use V1 only for a documented exception: the target Region does not support V2; an existing
application has an unresolved snapshot incompatibility; a required deployment tool cannot
configure V2 and the user cannot use a supported CLI/SDK path; a measured cost comparison favors
V1 for a cost-sensitive workload; or the user explicitly requires V1. A missing toolkit flag
alone is not an exception when the AWS SDK path below is usable. Higher unit prices alone do
not prove a higher bill. Check V1 availability and compatibility before using that fallback.
If the user explicitly requires V2, surface a blocking condition instead of silently using V1.

Missing evidence is **pending verification**, not evidence that V2 is unsupported. Keep V2
as the provisional recommendation, list the outstanding checks, and do not claim it is ready
to deploy. Unknown or `multi`/`global` Regions need concrete deployment Regions before deployment.
For non-AgentCore effective runtimes and Instances, set `agentcore_platform` to `null`.
An AgentCore split verdict consolidated onto ECS therefore has no AgentCore platform setting.
An unresolved effective AgentCore compute type remains pending; do not assume microVMs.

Record `agentcore_platform` in each applicable `design.json.units[]` entry:

```json
{
  "version": "V2",
  "status": "pending",
  "reason": "Default microVM platform; snapshot compatibility still needs verification.",
  "checks": [
    {
      "check": "region",
      "status": "verified",
      "source": "<public AWS URL observed in this run>",
      "detail": "<target Region and observed availability>"
    },
    {
      "check": "snapshot_compatibility",
      "status": "pending",
      "source": "<source paths or generated POC paths>",
      "detail": "<work still needed>"
    }
  ]
}
```

`version` is V1 or V2. `status` is `verified` only when all applicable checks have evidence;
otherwise it is `pending`. This is applicability evidence, not proof of an AWS deployment.
Include checks for deployment tooling and environment size as well as Region and snapshot
compatibility. For V1, `reason` names the concrete exception and its evidence. Mirror the primary
unit's whole record at the top level. Estimate, reports, migration plans, and POCs consume this
record; they do not select a version independently.

## Service facts to refresh

The following are **cached as of 2026-09-21**, not verification of a future run. Refresh the
profile's `platform_versions`, `v2_regions`, `v2_constraints`, and `microvms_memory_billing`
facts under `freshness.md`. Record actual lookup results, including failures. Versioned
CPU/memory unit rates in `microvms_pricing` remain dated cache inputs under Estimate
— they are not refreshed through MCP or reported as verified this run.

- V2 Regions: `us-east-1`, `us-east-2`, `us-west-2`, `eu-west-1`, `ap-northeast-1`.
- V2 environment variable total: direct code 1.5 KB; containers 2.5 KB (V1: 4 KB). Inspect
  the complete generated environment, including instrumentation variables. A two-variable
  example does not establish the final environment size.
- Create/update takes several minutes. Initialization must complete before the first healthy
  `/ping`, within 120 seconds. Poll for `READY` or failure before another update or delete.
- CloudFormation/CDK cannot currently set `platformVersion`. Verify the chosen CLI/SDK's
  support; do not invent an `agentcore launch --platform-version` flag.
- Startup is a restored initialization snapshot, not session suspend/resume. Larger compute,
  x86 microVMs, lifecycle hooks, and committed baseline discounts were announced as coming soon;
  do not enable them from the launch blog's roadmap.

Sources: [platform versions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html#runtime-platform-versions),
[launch announcement](https://aws.amazon.com/blogs/machine-learning/the-new-agentcore-runtime-elastic-optimized-and-consistently-fast-starts/),
and [pricing](https://aws.amazon.com/bedrock/agentcore/pricing/).

## Snapshot-compatible code

Follow the [V2 optimization guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-v2-optimize.html).
Keep reusable imports, bundled static configuration, model files, and reusable clients at
startup. Generate request IDs/random tokens and current timestamps in the handler; measure
elapsed time from a handler-local reference. Refresh expiring credentials and dynamic
configuration, including Gateway tool catalogs, instead of freezing their startup values.
Clients must reconnect after restore. Do not identify a worker by its hostname or PID.
For custom cryptographic libraries, use snapshot-safe builds (for example,
`openssl-snapsafe-libs` on Amazon Linux 2023); the direct-code managed base already provides them.

For existing agents, record the affected paths and necessary edits in the migration/POC plan.
After deployment, test new sessions, repeated requests, a request after an idle interval, and
credential refresh where applicable. Local HTTP success does not verify snapshot restore.

## Deploy and read back

Prefer a currently verified deployment tool that sets `platformVersion` on create/update.
The Python starter toolkit's `configure`/`launch` path can still package and provision a POC;
when it cannot select the platform, follow it with `scripts/set_agentcore_platform.py` copied
into the POC. That helper preserves the runtime configuration, explicitly updates the platform
if needed, allows up to 15 minutes for each readiness wait, and requires `GetAgentRuntime`
to return the requested platform and `READY`. The platform update receives a fresh wait budget
after the API accepts it. It refuses Instances. A failed update never triggers a V1 retry.

Before any resource-creating command, check SDK support and resolve the pending applicability
checks. Capture the exact runtime ID from the deployed project's config, not a name search.
Use one unit's ID, Region, and version together. The toolkit compatibility path may first
create V1; do not invoke it or call the deployment complete until the final version readback.
This is a POC deployment step, not authorization to update an unrelated existing runtime.

Save only the helper's ID/revision/platform/status output as `runtime-verification.json`
inside that unit's POC directory. Keep the full Get response, especially environment variables,
out of reports and logs. A create/update response, local `/ping`, or successful toolkit exit
does not prove the deployed platform. The first readback records the observed numeric revision;
it does not attest to a toolkit-requested revision that the toolkit has not supplied. The
helper's own update is checked against the revision returned by `UpdateAgentRuntime`; use
the application smoke test to validate deployed application behavior. Mode A has no deployment evidence until the user runs
the script. Harness retains its declarative deployment model; verify its target-specific
platform support and runtime ID, and use the same readback requirement without substituting
a custom-code POC. If deployment support remains unverified, leave an explicit blocking TODO.
