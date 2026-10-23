# Beyond single-instance EC2: advanced capacity paths

Read this when a single large instance acquired through the ladder is not enough: the workload is
multi-node distributed training, needs a managed resilient cluster, or is better served by a
managed training reservation or a purpose-built accelerator than by chasing scarce GPUs directly.
These are pointers to the mechanisms that own each path, framed by the startup constraint, not a
restatement of their mechanics.

Reach for anything here only after a single large instance has actually been shown to be the
bottleneck. Jumping to a multi-node cluster before that is the classic over-build: more capacity to
secure, more to pay for, more to operate, for a team with no platform function.

## Managed training reservations and sizing

A managed training service can reserve accelerated capacity for a training window and run the job
without you operating the cluster, which suits a startup with no ML platform team. The supported
instance types and Regions for managed training reservations change, so verify current support
rather than assuming it. Before deciding how much capacity to reserve, size the job against the
real model and data footprint.

- **`Skill("aws-core:aws-ai-ml")`**: managed training and inference capacity, training-reservation
  mechanics, and model-to-instance sizing. Use it to decide how much capacity to acquire before
  you reserve any.

## Managed resilient clusters for large or long training

A long multi-node training run on self-managed instances means you also own node failure recovery,
which a small team cannot staff. A managed resilient cluster handles hardware-failure recovery and
capacity orchestration for large accelerated jobs, and integrates with container orchestration. The
startup value is the resilience and the removed operational burden, not raw speed.

- **`Skill("aws-core:aws-ai-ml")`**: managed cluster options for large-scale training.
- **`Skill("aws-core:aws-containers")`**: when the cluster is driven through a container
  orchestrator, including capacity-type prioritization for GPU node pools.

## Multi-node interconnect and placement

Distributed training across many GPUs is bound by inter-node bandwidth, not just GPU count. High
inter-node throughput needs a high-bandwidth network interface between nodes and the nodes placed
close together. This only matters once a single node is proven insufficient; until then it is
complexity with no payoff.

- **`Skill("aws-core:aws-compute")`**: placement groups, high-bandwidth network interfaces for
  inter-node communication, and the launch mechanics for a tightly coupled multi-node job.

## Purpose-built accelerators as an alternative to scarce GPUs

Purpose-built AWS training and inference accelerators can offer better price-performance than
equivalent GPU instances, and because they are a different capacity pool, they can be available
when a specific GPU type is not. The trade-off is a software-stack migration: the workload must run
through the vendor-specific SDK, which is real engineering effort. For a startup, the question is
whether the price-performance gain and the extra availability are worth that migration cost for
this workload.

- **`Skill("aws-core:aws-ai-ml")`**: purpose-built accelerator options, the SDK path, and
  framework and model support, so you can judge the migration effort against the benefit.

## CPU as the overlooked alternative

Some inference and classical ML workloads run acceptably, and far more cheaply and reliably, on
CPU instances, because CPU capacity is far easier to get than GPU capacity. If a model fits in
memory after quantization or distillation, or the framework exploits CPU vector extensions,
evaluate CPU before competing for a scarce GPU at all. The most available capacity is the capacity
you do not need.

- **`Skill("aws-core:aws-compute")`**: memory-optimized and compute-optimized CPU families and
  their vector-extension capabilities.
- **`Skill("aws-core:aws-ai-ml")`**: when a model is a candidate for CPU inference, and the
  footprint-reduction techniques that make it fit.
