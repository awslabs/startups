---
name: gpu-capacity-strategy
description: "Use when securing and paying for scarce accelerated compute on AWS without the ability to sign a multi-year commitment, because the mechanisms that guarantee capacity require exactly the commitment a pre-revenue company cannot responsibly make. Covers matching the purchase model to the workload shape across on-demand, Spot, and Capacity Blocks, getting a GPU quota request actually approved, treating approved quota as distinct from available capacity, surviving Spot interruption mid-training through checkpoint and resume, and deciding when a managed per-token endpoint beats owning instances at real utilization. Also use when a GPU launch fails for capacity reasons, a quota request is stalled, or accelerated spend is outpacing runway. Not for model selection, inference code, or general instance-type selection, which belong to the aws-core skills upstream."
license: Apache-2.0
metadata:
  audience: startup
---

# GPU Capacity Strategy

For an AI startup, accelerated compute is usually both the largest line item and the hardest thing to actually obtain. This skill is about the procurement and resilience problem: getting capacity, holding it, and not going broke on it. For which model to run or how to write the inference path, use `amazon-bedrock` and `aws-ai-ml` in `aws-core`.

The specific bind for a small company: the purchasing mechanisms that guarantee capacity require commitment, and commitment is what a pre-revenue company cannot responsibly make. The answer is usually a deliberate mix rather than one purchase model.

## Match the purchase model to the workload shape

| Workload                               | Interruptible | Reasonable default                                              |
| -------------------------------------- | ------------- | --------------------------------------------------------------- |
| Experimentation, hyperparameter sweeps | Yes           | Spot, with checkpointing                                        |
| A known training run with a deadline   | No            | Capacity Block for the run window                               |
| Production inference, steady traffic   | No            | On-demand first, commit only after the traffic is proven        |
| Production inference, spiky traffic    | No            | Managed endpoint or serverless inference, so idle costs nothing |
| Batch or offline inference             | Yes           | Spot with a queue and retries                                   |

**Do not commit before the usage is stable.** A one or three year commitment signed against projected traffic is a bet on a projection, and the failure mode is paying for idle accelerators out of runway. Wait for a few months of real usage before converting steady demand into a commitment. This is the single most common way accelerated compute destroys a small company's margins.

**Consider not owning accelerators at all.** For many startups the correct answer is a managed model endpoint priced per token or per request, where idle costs nothing and there is no capacity to secure. Owning instances makes sense once utilization is high and sustained, or when you need a model or configuration that is not otherwise available. Compare against your real utilization, not peak.

## Getting quota actually approved

A GPU quota request that just names a number tends to sit. Requests move faster when they carry the operational detail a reviewer needs.

- Request the specific instance family and size in the specific region, not a general increase.
- State the intended use, the expected duration, and whether it is training or inference.
- Ask for what you will use soon rather than an aspirational ceiling. Large jumps attract scrutiny; incremental increases against demonstrated usage clear more easily.
- Existing utilization is the strongest evidence. Consistently using what you already have supports the case for more.
- Lead time is real. Start before the capacity is on the critical path, not the week of a launch.
- Involve your AWS account team. For accelerated capacity, they can advise on regional availability and the realistic path, which is information you cannot get from the console.

Quota is not capacity. An approved quota is permission to launch, not a guarantee that the instance type exists in that Availability Zone when you ask. Treat them as two separate problems.

## When capacity is genuinely unavailable

`InsufficientInstanceCapacity` on accelerated types is common and is about physical availability, not your account.

- Try other Availability Zones in the region. Availability varies per zone.
- Try other regions if data residency permits. This is often the fastest unblock.
- Consider an adjacent instance generation or size. A slightly older generation is frequently available when the newest is not, and for many workloads the throughput difference matters less than starting today.
- Consider AWS silicon. Trainium for training and Inferentia for inference are usually more available than the most contended GPU types and often cheaper per unit of throughput. The cost is porting effort, which is real but bounded for common frameworks. See `aws-ai-ml` in `aws-core`.
- For a known run with a deadline, a Capacity Block reserves accelerated capacity for a defined window. This is the mechanism that turns "we hope capacity exists on Tuesday" into a scheduled run.
- Retry with backoff across a list of zones and types rather than a single hardcoded target. A launch path that tries one configuration will fail on the day it matters.

## Surviving Spot interruption

Spot is the difference between affordable and unaffordable experimentation, and it is only usable if interruption is designed for.

- **Checkpoint to durable storage on an interval that makes losing the interval acceptable.** Checkpoint only to local disk and an interruption costs the whole run.
- Handle the interruption notice: stop accepting new work, flush a checkpoint, exit cleanly.
- Make the training entry point resume from the latest checkpoint by default, so a restart is automatic rather than a manual intervention at 3am.
- Spread across instance types and zones. A single type in a single zone is the most interruption-prone configuration.
- Keep the checkpoint write cheap enough that a frequent interval is affordable, and verify a resume actually works before relying on it. An untested resume path is not a resume path.
- Never put a customer-facing inference endpoint on Spot alone. Mixed capacity with on-demand as the floor, or a managed endpoint.

## Controlling inference cost as traffic grows

- Measure cost per request or per token as a first-class metric, not just total monthly spend. Total spend tells you there is a problem; per-unit cost tells you whether it is growth or regression.
- Idle accelerators are the largest avoidable waste. If traffic has troughs, scale down or use a mechanism that bills only for use.
- Batch where the product tolerates it. Throughput per accelerator improves substantially with batching, and it is usually the cheapest optimization available.
- Right-size the model to the task. A smaller model that meets quality requirements changes unit economics more than any infrastructure tuning.
- Confirm whether credits cover accelerated usage and when they expire. Capacity planning built on credits that expire mid-quarter produces a sudden bill against a fixed runway.

## Where the service depth comes from

Do not restate service mechanics here. Invoke the upstream skills directly.

- **`Skill("aws-core:aws-compute")`**: Instance families, Spot mechanics, Auto Scaling, and capacity errors.
- **`Skill("aws-core:aws-containers")`**: Fargate Spot and container capacity.
- **`Skill("aws-core:aws-ai-ml")`**: Model deployment, SageMaker endpoints, and AWS silicon porting.
- **`Skill("aws-core:amazon-bedrock")`**: Managed model invocation and per-token pricing.
- **`Skill("aws-agents:agents-deploy")`**: Agent and inference runtime deployment.
- **`Skill("aws-core:aws-billing-and-cost-management")`**: Pricing lookups and cost allocation.

Verify current instance availability, quota behavior, and pricing against those sources rather than from memory. This area changes faster than most, and stale accelerator specifics are worse than none.

## Anti-patterns

- Signing a multi-year commitment against projected rather than observed traffic.
- Treating an approved quota as guaranteed capacity.
- Requesting a large quota increase with no stated use case, duration, or region, then waiting.
- Spot training with checkpoints written only to local disk, or with a resume path nobody has tested.
- A customer-facing inference endpoint on Spot with no on-demand floor.
- A launch path hardcoded to one instance type in one Availability Zone.
- Tracking only total monthly spend, so a per-request cost regression hides inside traffic growth.
- Buying accelerators before checking whether a per-token managed endpoint is cheaper at your actual utilization.
- Planning capacity on credits without checking their expiry date.
