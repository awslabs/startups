# Idle Floor: One Warm Replica or Scale to Zero

A company with a committed GPU fleet can run a second replica for availability, because its idle hours are capacity the company pays for anyway. From a fixed ceiling, a second warm replica doubles the largest line in the break-even. So the choice here is between one warm replica with no redundancy and scale to zero, made explicitly and priced against measured cold start.

The cheapest self-managed deployment that answers instantly is one warm replica, billed every hour. The cheapest one at idle is zero replicas, which costs a cold start on the next request. This file prices only the GPU replica floor. Other resources that cost money at zero traffic (load balancers, NAT gateways, cluster control planes) belong in the break-even inputs in `references/self-host-or-managed.md`; check their current floors with `Skill("aws-core:aws-billing-and-cost-management")`.

## Measure cold start first

Neither option can be priced without the cold-start time on the target platform. Measure each part separately, several times, from a state with no GPU node running:

1. Capacity acquisition: from the scaling signal until an instance is running. GPU capacity can be unavailable in an Availability Zone, so record failures as well as durations.
2. Node or instance boot until it can run the engine container.
3. Image pull. Engine images are large; record the size.
4. Model weight load into GPU memory.
5. Engine warm-up (compilation and CUDA graph capture) until `/health` passes and the first request completes.

The sum is the time a user waits, or the time a fallback must cover. With a fleet it only matters at scale-out; with one replica or zero it is what every user meets after a deploy, a crash or an idle period, so shorten it before choosing:

- Stage model weights in Amazon S3 at an immutable revision with a manifest, as `references/prepare-model-and-input.md` in `Skill("aws-startups-solution-architecture:self-hosted-llm-batch-inference")` describes, and keep the engine image in Amazon ECR, not a public hub. Use `Skill("aws-core:aws-storage")` for the storage mechanics.
- The EKS user guide lists cold-start reductions for inference Pods: SOCI parallel image pull (on by default in EKS Auto Mode for GPU instances), streaming weights from S3 to GPU memory, ECR over a VPC endpoint, and instance store caching ([Run AI/ML inference workloads on Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/ml-inference.html)).
- vLLM documents reusing its compile cache, and `--enforce-eager`, which skips CUDA graph capture at a cost in steady-state decode speed ([optimization and tuning](https://docs.vllm.ai/en/v0.31.0/configuration/optimization/)).
- Gate traffic on readiness, because a request routed to a replica that is still loading fails. Both engines expose `/health`. On ECS with a load balancer, set the service's health check grace period longer than the measured start; the default is 0 ([ECS CreateService API reference](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_CreateService.html), `healthCheckGracePeriodSeconds`). On Kubernetes, size a startup probe the same way.

## Option A: one warm replica

Keep exactly one replica running.

- Cost: the instance's hourly price for every hour of the month, plus storage for weights and the image.
- What fails: deploys, node replacement, an engine crash, and Availability Zone problems all take the only replica out. Decide what users see during those minutes and write it down. Common answers are a retryable error that the client handles, or a fallback described below.
- Deploys: a rolling update that starts the new replica before stopping the old one runs two GPU instances for the length of one cold start. That is usually cheaper than downtime; record it as a known cost.
- Health: alarm on the replica being unavailable, because there is no second replica to hide it. Use `Skill("aws-core:aws-observability")` for the alarm.

Choose A when idle hours are short, the latency target leaves no room for a cold start, and the break-even shows traffic already covers the floor.

## Option B: scale to zero

Remove the last replica when traffic stops, and start one on the next request.

- Cost: instance hours only while traffic exists, plus the cost of whatever covers requests during cold start.
- Scaling signal: something must observe a request while no replica exists, because with no registered target an Application Load Balancer returns HTTP 503 ([ALB troubleshooting](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-troubleshooting.html)). Use a queue or gateway in front of the engine that can hold or count requests, and scale on that. The platform mechanics (Karpenter node provisioning, ECS service desired count, EC2 Auto Scaling group minimum of zero) belong to `Skill("aws-core:aws-containers")` and `Skill("aws-core:aws-compute")`.
- Scale-in delay: how long to wait after the last request before removing the replica. Set it from the hourly traffic profile, and include it in the break-even, since those minutes are billed.

Requests that arrive during a cold start need one of these, decided in advance:

- Hold them. Works for near-interactive work where the client can wait longer than the measured cold start.
- Reject them with a retryable error. Works when the client retries with backoff and users tolerate the delay.
- Send them to a managed per-token model with the same prompt contract until the replica is ready. This keeps the product responsive at the cost of per-token spend during cold starts, and it requires the evaluation set to pass on both models. It is often the cheapest way to meet a latency target without a warm floor.

Choose B when there are long idle periods (nights, weekends, a product with bursty use) and one of the three cold-start answers is acceptable.

A scheduled middle ground is valid: warm during the hours the profile shows steady traffic, zero outside them. Price it in the same script.

On EC2 Auto Scaling, a warm pool of stopped, pre-initialized instances skips boot and setup on scale-out; `Skill("aws-core:aws-compute")` covers its mechanics and limits. For the floor, what matters is that a stopped instance is not billed for instance usage but its EBS volumes are, and the weights still load into GPU memory on every start, so measure the start again with the warm pool in place. Read the [warm pool limitations](https://docs.aws.amazon.com/autoscaling/ec2/userguide/ec2-auto-scaling-warm-pools.html) before using one under EKS or ECS, where an instance can register with the cluster while it is still initializing.

## Spot on a single replica

Spot lowers the hourly price of the only replica, and adds a failure mode. EC2 sends a Spot interruption notice two minutes before it interrupts the instance ([Initiate a Spot Instance interruption](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/initiate-a-spot-instance-interruption.html)). A fleet loses one replica of many; with one replica, an interruption means no capacity until a replacement completes a full cold start, and GPU Spot capacity may not be available for the replacement.

Use Spot for the single replica only when the cold-start answer from Option B is already in place, so an interruption is handled the same way as scale from zero. Test it with a controlled interruption before relying on it. Without such a fallback, keep the single replica on On-Demand.

## Do not keep empty GPU nodes

On EKS with Karpenter, an empty node is billed until consolidation removes it. Karpenter's `consolidateAfter` sets how long a node must be stable before it becomes a consolidation candidate, and the timer resets whenever a pod is added to or removed from the node ([Karpenter disruption](https://karpenter.sh/docs/concepts/disruption/)). A GPU NodePool with `consolidationPolicy: WhenEmpty` and `consolidateAfter: 72h`, as in the Startup Advisor prompt-library example for vLLM on EKS, keeps an empty GPU node for three days after its last pod leaves. Set the GPU NodePool's `consolidateAfter` from the measured scale-in delay instead, and verify after a scale-in that the GPU node is gone, not only the pod.

The same check applies on ECS and EC2: after the service or group reaches zero, confirm that no GPU instance is still running.
