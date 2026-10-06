# Capacity acquisition ladder

How to acquire GPU capacity when the team cannot sign a multi-year commitment and the account is
still building its usage history. There is no single best mechanism; there is a best match for a
workload under those constraints. Match first, then launch.

## Decision table

| Mechanism                          | Commitment                        | Idle cost                              | Behaviour on a cold account                                                                           | Best match                                                                           |
| ---------------------------------- | --------------------------------- | -------------------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| **Spot**                           | None                              | None (pay only while running)          | Often the most available path, since smaller and older types sit in Spot more than the newest P nodes | Interruptible, stateless, or checkpointed work: dev, batch, fault-tolerant inference |
| **Capacity Blocks for ML**         | Days to weeks (the block)         | Paid up front for the block            | Must be satisfiable for your account in the Region; warm up first                                     | A known, schedulable training window                                                 |
| **On-Demand Capacity Reservation** | None if immediate, else committed | On-demand price whether or not you run | Subject to the same account capacity standing                                                         | Capacity assurance held for any duration, immediate or future-dated                  |
| **On-demand (no reservation)**     | None                              | None                                   | Hits the Insufficient Capacity error first on a cold account                                          | Small, immediate, flexible launches while warming up                                 |

The through-line: a startup that cannot commit capital for years should default to the no-commitment
options (Spot, on-demand) while warming the account, and reach for a reservation only for a
specific, scheduled, high-value window it can now actually land.

## Spot first for the right workload

Spot is EC2 spare capacity at a steep discount and no commitment, which makes it the most
startup-aligned purchase option. It can be reclaimed, so it only fits work that tolerates
interruption: development, batch jobs, and fault-tolerant inference. Two things make it work in
practice:

- **Checkpoint and resume.** A reclaim must cost you minutes, not the whole run. Persist state
  often enough that an interruption is cheap.
- **Have a fallback.** When Spot capacity is unavailable, fall back to on-demand or a different
  type rather than blocking. When GPU nodes are scheduled through a container orchestrator, the
  cluster autoscaler can prioritize capacity types automatically; `Skill("aws-core:aws-containers")`
  owns that configuration, including preferring reserved, then Spot, then on-demand.

Because smaller and older accelerated instances sit in the Spot pool more often than the newest,
scarcest P-family nodes, Spot also rewards the size and type flexibility described below.

## Capacity Blocks for ML: the reservation that fits a startup

Capacity Blocks let you reserve a GPU cluster for a fixed future window and pay for the block, with
no ongoing commitment past it. The AWS documentation describes them as a way to "reserve GPU-based
accelerated computing instances on a future date to support your short duration machine learning
(ML) workloads," paying "only for the amount of time that you need." Instances in a block are
"automatically placed close together inside Amazon EC2 UltraClusters" for low-latency
interconnect. That is the reservation model that actually matches a startup, because the
commitment is measured in days, not years.

The documented bounds also set the scale of a reservation request. You can reserve a block with a
start time "up to eight weeks in the future," each block can hold "up to 64 instances," and you
can have "up to 256 instances across Capacity Blocks." A request near those ceilings from a cold
account is the kind of large reservation that fails without a warmed-up account behind it.
Supported instance types and the Regions they are offered in change over time, so verify current
support in the AWS console or documentation rather than from memory, and verify the price at
reservation time.

Find and purchase a block from the CLI:

```
aws ec2 describe-capacity-block-offerings \
  --instance-type p5.48xlarge \
  --instance-count 16 \
  --start-date-range 2026-11-01T00:00:00Z \
  --end-date-range 2026-11-08T00:00:00Z \
  --capacity-duration 48
```

```
aws ec2 purchase-capacity-block \
  --capacity-block-offering-id cbr-0123456789abcdefg \
  --instance-platform Linux/UNIX
```

## On-Demand Capacity Reservation for steady, flexible-term capacity

On-Demand Capacity Reservation (ODCR) lets you "reserve compute capacity for your Amazon EC2
instances in a specific Availability Zone for any duration," so you "always have access to Amazon
EC2 capacity when you need it, for as long as you need it." The AWS documentation defines two
forms. A reservation **for immediate use** "becomes available for use immediately and there is no
term commitment"; you can "modify" or "cancel it at any time to release the reserved capacity and
to stop incurring charges." A **future-dated** reservation has you "specify when you need the
capacity and how long you commit to keeping it," and during the commitment duration you cannot
decrease the instance count or duration below the initial commitment, with a possible cancellation
charge. You pay the on-demand rate whether or not you run instances in the reserved capacity, so
it fits capacity you will actually keep busy.

Immediate reservation:

```
aws ec2 create-capacity-reservation \
  --availability-zone az_name \
  --instance-type instance_type \
  --instance-count number_of_instances \
  --instance-platform operating_system \
  --instance-match-criteria open
```

Future-dated reservation:

```
aws ec2 create-capacity-reservation \
  --availability-zone az_name \
  --instance-type instance_type \
  --instance-count number_of_instances \
  --instance-platform operating_system \
  --instance-match-criteria targeted \
  --delivery-preference incremental \
  --commitment-duration commitment_in_seconds \
  --start-date YYYY-MM-DDThh:mm:ss.sssZ
```

`Skill("aws-core:aws-billing-and-cost-management")` owns the current rates and the comparison of a
reservation against on-demand and Spot for your utilization.

## Diversify, and probe before you commit

A single rigid request (one type, one AZ, one Region, right now) is the hardest thing to satisfy
from a cold account. Flexibility on any axis is often the difference between a stuck launch and a
running job.

- **Size and type.** Accept a different size in the family or a different accelerated family when
  it fits. `Skill("aws-core:aws-compute")` owns which are interchangeable for a workload.
- **Availability Zone and Region.** Each has its own capacity pool. A popular GPU type exhausted
  in the obvious Region is often available elsewhere. Hold compliance boundaries (data residency,
  GDPR) fixed, and confirm any cross-Region move with a human before doing it.
- **Time.** Capacity frees up at different times; an overnight or next-day run often lands when a
  right-now one does not.

### Probe which offerings and Regions actually have capacity

Before committing a launch, check where an accelerated instance type is even offered, and compare
Spot pricing as an availability signal across Availability Zones:

```
# Which AZs in the current Region offer this instance type at all
aws ec2 describe-instance-type-offerings \
  --location-type availability-zone \
  --filters Name=instance-type,Values=g6.xlarge \
  --query 'InstanceTypeOfferings[].Location' --output text
```

```
# Recent Spot price per AZ, a proxy for where Spot capacity is healthier
aws ec2 describe-spot-price-history \
  --instance-types g6.xlarge \
  --product-descriptions "Linux/UNIX" \
  --start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --query 'SpotPriceHistory[].[AvailabilityZone,SpotPrice]' --output text
```

Repeat across candidate Regions by adding `--region`. A type that is not offered in a Region will
never launch there regardless of quota, so this is the cheapest first check.

## When self-service runs out

If you have climbed the ladder, warmed the account, diversified, and still cannot land the
capacity, that is a real wall, and the point to raise it with AWS, with lead time. This is an
escalation for a genuinely stuck launch, not a substitute for the warm-up and flexibility work
above, which resolves most cases without it.

Do not assume a startup has a dedicated AWS contact; many self-onboarded startups do not. The
paths that are open regardless:

- **Your AWS account team, if you have one.** Some startups have an assigned AWS account team;
  if yours does, raise the capacity need with them early, with the use case and the dates, ahead
  of the deadline rather than on the day. Do not assume one exists.
- **AWS Activate.** If the startup is in AWS Activate (directly or through an accelerator,
  incubator, or VC), that program is a documented route to AWS guidance and support. Check
  Activate standing before assuming there is no one to talk to.
- **A support case is a path.** A capacity or quota-increase request through AWS Support is open
  to any account. File it with lead time and the real workload behind it.
