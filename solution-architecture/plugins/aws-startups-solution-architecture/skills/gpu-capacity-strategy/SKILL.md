---
name: gpu-capacity-strategy
description: "Use when a startup needs assured access to accelerated compute but cannot sign the multi-year commitment that AWS sells assurance through, so the usual answer of a Savings Plan or Reserved Instance is unavailable. Covers the commitment-free ladder from managed per-token endpoints through on-demand to Capacity Blocks, why a Capacity Block is the one assurance mechanism priced as a window rather than a term, how to decide when observed utilization finally justifies committing, why credits are not runway and what their expiry does to a capacity plan, and the fixed monthly floor a design carries at zero traffic. Not for capacity errors, quota mechanics, Spot behavior, instance selection, model choice, or inference tuning: those are general AWS mechanics owned by the aws-core skills and must not be restated here."
license: Apache-2.0
metadata:
  audience: startup
---

# GPU Capacity Strategy

Accelerated compute is usually a startup's largest line item and the hardest thing to actually obtain. This skill addresses one decision only: **how to get capacity assurance without buying it the way AWS sells it.**

The bind is structural. The mechanisms that guarantee accelerated capacity, Savings Plans and Reserved Instances, are priced as one or three year terms. A pre-revenue company cannot responsibly sign a term longer than its runway. So the standard answer to "how do I guarantee capacity" is unavailable, and the question becomes which commitment-free instrument to use instead.

Everything about _how_ capacity, quota, and Spot behave is general AWS mechanics. Do not reason about it here; pull it from the upstream skills below and spend the reasoning on the commitment decision.

## The commitment-free ladder

Climb only as far as observed usage justifies. Each rung buys more assurance and costs more optionality.

| Rung                              | Assurance                        | Commitment         | Use when                                                              |
| --------------------------------- | -------------------------------- | ------------------ | --------------------------------------------------------------------- |
| Managed per-token endpoint        | None needed, no capacity to hold | None               | Utilization is low or spiky, and a hosted model meets the requirement |
| On-demand                         | None                             | None               | Usage is real but not yet stable enough to characterize               |
| Capacity Block                    | Guaranteed for a defined window  | The window only    | A specific run has a deadline                                         |
| Savings Plan or Reserved Instance | Strongest                        | One or three years | Only after months of observed steady usage                            |

**The Capacity Block is the instrument that resolves the bind.** It is the only assurance mechanism priced as a window rather than a term, so it converts "we hope capacity exists on Tuesday" into a scheduled run without mortgaging runway. When a training deadline is real and a commitment is not signable, this is the rung to reach for.

**Consider staying on rung one indefinitely.** Owning accelerators only pays once utilization is high and sustained, or a required model is not otherwise hosted. Compare a managed endpoint against _actual_ utilization rather than peak: a startup that sizes for peak and runs at ten percent has bought idle capacity out of runway.

## Deciding when to finally commit

The commitment is correct eventually. Getting the timing wrong in either direction is expensive, so decide it on observed data rather than a forecast.

- **Require months of steady observed usage**, not a projection. A term signed against a forecast is a bet, and the losing outcome is paying for idle accelerators out of runway. This is the single most common way accelerated compute destroys a small company's margins.
- **Commit to the floor, not the peak.** Cover only the baseline that has been continuously present, and leave the variable portion on-demand. Over-committing is much harder to unwind than under-committing.
- **Check the term against the runway.** A three year commitment made with eighteen months of cash is a bet on a raise, not a capacity decision. Say that out loud when it is what is happening.

## Credits are not runway

Credits change what is affordable while they last, and their expiry is a cliff rather than a slope.

- Confirm whether credits apply to accelerated usage at all before planning capacity around them. Coverage is not uniform.
- Model the first month _after_ expiry at current usage. If that number is a surprise, the plan has an undisclosed cliff.
- A capacity plan whose economics depend on credits expiring after the next raise is a fundraise assumption wearing an infrastructure costume.

## Know the floor at zero traffic

Some accelerated and adjacent services bill a fixed minimum whether or not anything is running, and several such floors in one design produce a monthly bill nobody budgeted.

Add up what the design costs at zero traffic and state that number. Verify current minimums with `Skill("aws-core:aws-billing-and-cost-management")` rather than from memory, since they change.

## Upstream skills to defer to

Do not restate the mechanics these own. Invoke them directly:

- **`Skill("aws-core:aws-compute")`**: Capacity errors including `InsufficientInstanceCapacity`, Spot mechanics and interruption handling, quota and limit behavior, instance family and generation selection, and Auto Scaling.
- **`Skill("aws-core:aws-ai-ml")`**: SageMaker endpoints, model deployment, and porting to AWS silicon.
- **`Skill("aws-core:amazon-bedrock")`**: Managed model invocation and per-token pricing.
- **`Skill("aws-core:aws-billing-and-cost-management")`**: Pricing lookups, service minimums, commitment analysis, and cost allocation.
- **`Skill("aws-core:aws-containers")`**: Container and Fargate capacity.
- **`Skill("aws-agents:agents-deploy")`**: Agent and inference runtime deployment.

Accelerator availability and pricing move faster than most of AWS. Stale specifics are worse than none, so verify against those sources rather than recalling numbers.

## Anti-patterns

- Signing a term commitment against projected rather than observed usage.
- Committing to peak instead of the continuously present baseline.
- A commitment term longer than the runway, presented as a capacity decision rather than a bet on a raise.
- Planning capacity on credits without confirming they cover accelerated usage, or without modeling the month after expiry.
- Buying accelerators before comparing a managed per-token endpoint at real, not peak, utilization.
- Shipping a design without adding up its cost at zero traffic.
- Reaching for a term commitment when a Capacity Block would cover the actual need.
