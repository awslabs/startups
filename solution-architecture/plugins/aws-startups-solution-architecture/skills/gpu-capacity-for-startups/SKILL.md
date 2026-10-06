---
name: gpu-capacity-for-startups
description: "This skill should be used when a startup cannot launch the GPU instances it needs on AWS, is deciding how to secure GPU capacity it cannot commit to for years, or is planning capacity ahead of a training run, launch, or demo on a hard deadline. The reshaping constraint is that a young, lightly used AWS account carries little quota and no capacity track record, so the account must be warmed up before large reserved GPU blocks are reachable, and the team has no capacity-planning function to absorb a stuck launch. Covers the warm-up ladder from small on-demand instances to large reservations, matching an acquisition mechanism (Capacity Blocks, On-Demand Capacity Reservation, Spot with fallback, training reservations) to a workload that cannot sign a multi-year deal, diversifying across size, Availability Zone, Region, and time, and treating quota as lead-time-bound before an event. Not for choosing the fastest GPU family or writing the launch mechanics, which belong to aws-core:aws-compute."
license: Apache-2.0
metadata:
  audience: startup
---

# GPU Capacity for Startups

A startup rarely fails to get GPUs because it picked the wrong instance family. It fails because
a young AWS account has almost no accelerated-compute quota, no history that earns a quota
increase quickly, and no capacity-planning function to fall back on when a launch is one Insufficient
Capacity error away from slipping a funding-milestone deadline. The instance choice is the part
`aws-core:aws-compute` already answers. The part that actually blocks a startup is reaching the
capacity at all, from an account that has not earned it yet.

Treat two constraints as primary, because they are what change the answer from the general one:

- **The account is young and lightly used, so quota is low and trust is unbuilt.** This is the
  explicit difference from an enterprise. An enterprise scales GPU workloads out of established
  accounts that already carry a usage history, so their accelerated-compute quotas are already
  raised. A startup starts from a brand-new account, where the GPU quotas sit at zero. The Service
  Quotas documentation states plainly that an account's actual quota "may be less than the AWS
  default quota value if the account was recently created or if you use the account minimally."
  That limit does not rise on its own: for an adjustable quota you raise it by submitting a quota
  increase request through AWS Service Quotas, and the documentation notes that "larger increase
  requests take time to review, process, approve, and deploy." You cannot request your way from
  zero to a 64-GPU reservation on a two-week-old account on the morning of the launch, so the
  ordering has to plan for that.
- **The team cannot commit capital for years and has no one whose job is capacity planning.** The
  acquisition mechanism has to match a company that may pivot in a quarter, not one signing a
  three-year hardware deal.

Both push toward the same discipline: start small and flexible, build the account's usage and
quota deliberately before you need the big reservation, and reserve only once the account can
actually land it.

## The warm-up ladder: do not start at the top

The single most common startup failure here is launching an account and immediately requesting
the largest GPU instances or asking for a large reservation, hitting a quota wall or an
Insufficient Capacity error, and reading it as "AWS has no GPUs." The account simply has not
earned that capacity yet.

Climb deliberately instead:

1. **Start small and prove the workload.** Run the smallest accelerated instance that fits the
   job (a single-GPU G instance), or even a CPU instance for early development, before reaching
   for a P-family multi-GPU node. Early development, debugging, and inference prototyping rarely
   need the biggest instance, and a smaller one both launches more reliably on a cold account and
   starts building usage history. See `references/capacity-acquisition-ladder.md`.
2. **Grow usage, then request more quota.** You raise an adjustable quota by requesting an
   increase through AWS Service Quotas; usage does not raise it on its own, though consistent real
   usage strengthens the case. Request quota increases incrementally and tied to a real workload,
   ahead of the need rather than during the incident. Quota is lead-time-bound, not instantaneous.
3. **Reserve only once the account can land it.** Capacity Blocks for ML and On-Demand Capacity
   Reservation are the right tools for a committed training window, but a reservation request
   still has to be satisfiable for your account in that Region. Warm up first, reserve second.

`references/account-warm-up-and-quota.md` carries the quota mechanics: how recency and low usage
suppress quota, which accelerated-compute quotas to raise and in what order, how to request an
increase ahead of need, and why the request has to lead the launch by days or weeks.

## Match the mechanism to a startup that cannot commit for years

There is no single best way to get GPU capacity. There is a best match for a workload under
startup constraints. The decision table and the trade-offs, including what each mechanism costs
when idle and how each behaves on a cold account, are in
`references/capacity-acquisition-ladder.md`. The shape of the decision:

- **Interruptible or stateless work (dev, batch, fault-tolerant inference): Spot first.** Spot is
  spare capacity at a steep discount and is the most startup-aligned purchase option, with no
  commitment. It can be reclaimed, so it needs checkpointing and a fallback, but for the right
  workload it is both the cheapest and often the most _available_ path, because smaller and older
  instance types sit in Spot more often than the newest P-family nodes.
- **A known, time-boxed training window you can schedule: Capacity Blocks for ML.** You reserve a
  cluster for a fixed future window and pay for the block, with no multi-year commitment. This is
  the reservation model that actually fits a startup, because the commitment is days, not years.
- **Steady capacity you want held at on-demand price: On-Demand Capacity Reservation.** Reserve
  now or future-dated, modify or cancel when the commitment ends. Wider instance-type coverage
  than Capacity Blocks, charged at on-demand whether or not you run.
- **Managed training or large-cluster capacity: training reservations and managed clusters.**
  Covered as a pointer, not restated, in `references/beyond-ec2-and-advanced.md`.

## Diversify, because a single rigid ask is the thing that fails

A startup that insists on one exact instance type, in one Availability Zone, in one Region, right
now, has given AWS the hardest possible request to satisfy from a cold account. Flexibility on any
axis is what turns a failed launch into a running job:

- **Size and type flexibility.** Accept a different size in the family, or a different accelerated
  family, when it fits the workload. `aws-core:aws-compute` owns which families are interchangeable
  for a given job.
- **Availability Zone and Region flexibility.** Every Region and AZ has its own capacity pool.
  Popular GPU instances are often exhausted in the obvious Region and available in another. Keep
  compliance boundaries (GDPR, data residency) in view, and confirm them with a human before
  moving a workload across a Region boundary.
- **Time flexibility.** Capacity frees up at different times. A job that can run overnight or
  shift a day often lands when a right-now launch does not.

Details, including how to probe which Regions and AZs actually have capacity before you commit a
launch, are in `references/capacity-acquisition-ladder.md`.

## Reference files

- **`references/account-warm-up-and-quota.md`**: Read first when the blocker is a young account,
  a quota wall, or an Insufficient Capacity error on a new account. Covers why recent or minimal
  use suppresses quota, the warm-up ladder from small to large, which accelerated-compute quotas
  to raise and in what order, requesting an increase ahead of need, and treating quota as
  lead-time-bound before a launch or event.
- **`references/capacity-acquisition-ladder.md`**: Read when choosing how to acquire capacity
  under the no-multi-year-commitment constraint. Decision table across Spot, Capacity Blocks for
  ML, On-Demand Capacity Reservation, and diversification, including idle cost, cold-account
  behavior, the failure mode of each, and probing Regions and AZs for real capacity before
  committing.
- **`references/beyond-ec2-and-advanced.md`**: Read when the single-account, single-cluster path
  is not enough: managed training reservations, managed resilient clusters, multi-node
  interconnect and placement for distributed training, and purpose-built accelerators as an
  alternative to scarce GPUs. Points to the upstream skills that own each mechanism rather than
  restating them.

## Upstream skills to defer to

Do not restate the mechanics these own. Invoke them directly and spend the reasoning on the
capacity decision under startup constraints:

- **`Skill("aws-core:aws-compute")`**: Accelerated instance families, which are interchangeable
  for a workload, EC2 purchase-option mechanics, and launch templates.
- **`Skill("aws-core:aws-billing-and-cost-management")`**: Current GPU and reservation pricing,
  idle cost floors, and comparing a reservation against on-demand and Spot.
- **`Skill("aws-core:aws-ai-ml")`**: Managed training and inference capacity, and model-to-instance
  sizing before you decide how much capacity to acquire.
- **`Skill("aws-core:aws-containers")`**: Cluster autoscaling capacity-type prioritization when GPU
  nodes are scheduled through a container orchestrator.
- **`Skill("aws-core:aws-observability")`**: GPU utilization metrics, so a scarce reserved instance
  is not sitting idle.

For which managed inference or training service fits before any of this applies, use
`Skill("aws-startup-advisor:architect-for-startups")`.

## Anti-patterns

- Launching the largest GPU instances or a large reserved block on a brand-new account, hitting a
  wall, and concluding AWS has no capacity, rather than warming the account up first.
- Requesting a quota increase during the launch incident instead of days or weeks ahead, when it
  is lead-time-bound.
- Pinning to one instance type, in one Availability Zone, in one Region, right now, which is the
  hardest request to satisfy from a cold account.
- Signing a long, inflexible capacity commitment to guarantee access, when a startup's roadmap may
  not survive the commitment term.
- Using Spot for interruptible work with no checkpointing or fallback, so a reclaim loses the run.
- Buying a reservation and then leaving it idle, paying for scarce capacity that no job is using,
  with no utilization metric watching it.
- Reaching for a multi-node cluster and its interconnect before a single large instance has been
  shown to be the bottleneck.
