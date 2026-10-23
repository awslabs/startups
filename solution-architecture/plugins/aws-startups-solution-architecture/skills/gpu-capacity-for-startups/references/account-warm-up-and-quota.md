# Account warm-up and quota strategy

Field notes on the constraint that reshapes GPU access for a startup: a young, lightly used AWS
account does not have the quota or the capacity standing to launch large accelerated instances,
and nobody on the team is a capacity planner. Treat quota as something you build before you need
it, not something you request in the middle of a stuck launch.

## Why a new account starts capacity-poor

The AWS Service Quotas documentation says it directly: an account's actual quota value "may be
less than the AWS default quota value if the account was recently created or if you use the
account minimally." Two things follow for a startup:

- A brand-new account can sit _below_ the published default for accelerated-compute quotas. The
  default is a ceiling you grow into, not a floor you start at.
- The applied quota does not rise on its own as you use the account. For an adjustable quota you
  raise it by submitting a quota increase request through AWS Service Quotas when you need more.
  Demonstrated, consistent usage over time is what makes the account a candidate for a higher
  limit, but you still have to ask for the increase; running workloads does not grant it
  automatically.

The practical consequence: the morning of a launch is the worst possible time to discover the
account cannot launch what the launch needs.

## The warm-up ladder

Climb from small and reliable to large and reserved. Each rung both de-risks the launch and
builds the usage history that makes the next rung reachable.

1. **Develop and prototype on the smallest thing that works.** Early development, debugging, and
   small-scale inference rarely need a multi-GPU P-family node. A single-GPU G instance, or even
   a CPU instance for parts of the pipeline, launches far more reliably on a cold account and
   starts accumulating the usage record. `Skill("aws-core:aws-compute")` owns which specific
   family fits a given workload; the point here is to not reach for the biggest one first.
2. **Scale instance size and count gradually.** Move up in size and number as the workload proves
   it needs it, rather than requesting the top of the range on day one. Each successful larger
   launch is itself evidence for the next quota increase.
3. **Request quota increases incrementally and ahead of need.** Raise the specific
   accelerated-compute quota you are about to need, in a reasonable increment tied to a real
   workload, before the launch window, not during it.
4. **Reserve large capacity only once the account can land it.** A warmed-up account with a real
   usage history and raised quotas is the one that can actually get a Capacity Block or a large
   On-Demand Capacity Reservation satisfied.

Do not read a quota wall or an Insufficient Capacity error on a new account as "AWS is out of
GPUs." On a cold account it almost always means the account has not earned that capacity yet.

## Which quotas, and in what order

Accelerated-compute quotas are per family and per Region, and most are adjustable. The ones that
matter for GPUs are the running On-Demand instance quotas for the P and G families, and the
corresponding Spot instance request quotas if you intend to use Spot. Many AWS services carry
their own separate quotas, so check the service you depend on as well, not only EC2.

- Raise the quota in the exact Region you intend to launch in. Quota is per Region.
- Raise On-Demand and Spot quotas separately; they are distinct limits.
- Ask for a reasonable increment tied to a real need, and submit it ahead of the launch window.
- A higher limit comes from requesting an increase, not from usage alone. The AWS Service Quotas
  documentation describes requesting a quota increase for an adjustable quota, and notes that
  "larger increase requests take time to review, process, approve, and deploy." Building real
  usage on the account strengthens the case for a higher limit, but you still submit the request;
  it is not granted automatically.

### Inspect current quotas from the CLI

View the default quota values for a service (EC2 shown; find other service codes with
`aws service-quotas list-services`):

```
aws service-quotas list-aws-default-service-quotas \
  --service-code ec2
```

Retrieve the quota values actually applied at the account level for a service (OpenSearch, whose
service code is `es`, shown as the example from the AWS documentation):

```
aws service-quotas list-service-quotas \
  --service-code es \
  --quota-applied-at-level ACCOUNT
```

Request an increase through the Service Quotas console, or with
`aws service-quotas request-service-quota-increase` once you have identified the quota code for
the specific accelerated-compute limit and Region. `Skill("aws-core:aws-compute")` and the
Service Quotas console both help map a family to its quota code.

## Treat quota as lead-time-bound before a launch or event

A launch, a demo for an investor, a training run tied to a milestone: these have fixed dates, and
quota increases and capacity reservations have lead time. The AWS Service Quotas documentation is
explicit that increase requests are "not granted immediately" and that it "might take a couple of
days for your increase to take effect," and Support "might approve, deny, or partially approve"
the request. Plan the capacity the way you would plan any other dependency with a lead time.

- Work backward from the event date. If you need N GPUs for a window, confirm the account can
  launch a smaller count now, request the quota increase with margin, and reserve the window with
  enough runway for the request to be satisfied.
- Prove the launch at small scale on the real account before the event, so the first time you run
  the large configuration is not live.
- If the account genuinely cannot get there in time through self-service, that is the point to
  raise it with AWS through whatever support channel the account has (see
  `references/capacity-acquisition-ladder.md`), with lead time, not on the day.

## Monitor so a hard-won instance is not wasted

Scarce reserved capacity sitting idle is money a startup cannot spare. Once you have GPU capacity,
watch its utilization so you keep what you use and release what you do not.
`Skill("aws-core:aws-observability")` owns the metric and alarm mechanics for GPU utilization.
