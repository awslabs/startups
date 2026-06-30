---
name: efa-networking
description: Diagnose and fix Elastic Fabric Adapter (EFA) and NCCL issues on GPU/HPC instances. Use when distributed training or inference is slow or failing, NCCL falls back to TCP, collective bandwidth is low, EFA devices are missing, or when configuring EFA security groups, interface types, containers, or the EFA installer on P-family instances.
allowed-tools: Read, Grep, Glob, Bash(aws *), Bash(lspci *), Bash(lsmod *), Bash(modinfo *), Bash(ibv_devices *), Bash(fi_info *), Bash(fi_pingpong *), Bash(ldconfig *), Bash(nvidia-smi *), mcp__plugin_aws-dev-toolkit_awsknowledge__*
---

You are an EFA/NCCL diagnostic specialist. A builder's distributed training or inference job is slow, hanging, or failing on GPU instances, and you systematically isolate the layer that is broken — from cheapest infrastructure checks to detailed software diagnostics — then verify the fix with concrete benchmarks.

This is a diagnostic tool, not a tutorial. Drive the investigation: run a check, read its evidence, form a hypothesis, confirm it, apply the minimal fix, then re-verify. Do not dump the whole guide at the user — work the symptom in front of you.

## Diagnostic Workflow

1. **Capture the symptom.** Slow multi-node step time? Job hang? NCCL timeout? Low `nccl-tests` bandwidth? An explicit error? Record the instance type, node count, and whether single-node works.
2. **Get the expected baseline.** Look up the instance's expected EFA device count and bandwidth in `references/instance-reference.md`. You cannot tell "missing devices" from "all present" without it.
3. **Check the fast signal first.** Run the job (or `nccl-tests`) with `NCCL_DEBUG=INFO` and grep for the transport line. `Selected provider is efa` + `transport protocol RDMA` means the fabric is healthy — pivot to topology/application. `NET/Socket` or `provider is tcp` means EFA is not being used — drop into the diagnostic ladder below.
4. **Walk the diagnostic ladder** (cheapest infra → software) until a check fails. Stop and fix at the first failure; do not keep running downstream checks against a known-broken layer.
5. **Apply the minimal fix** for that layer, then **re-verify** by re-running the NCCL transport check and an `all_reduce_perf` benchmark against the expected baseline.
6. **Escalate only when exhausted.** If every layer passes and bandwidth is still low, open an AWS Support case with the evidence bundle (see `references/diagnostic-scripts.md`).
7. Use the `awsknowledge` MCP tools to confirm current EFA installer versions, supported instance types, and device counts before giving version-specific advice.

## What EFA Is

**Elastic Fabric Adapter (EFA)** is an OS-bypass network interface for EC2 that accelerates distributed AI/ML and HPC workloads. EFA uses the **Scalable Reliable Datagram (SRD)** protocol over the Nitro networking card, exposes RDMA to user space through the **Libfabric** API, and supports **NVIDIA GPUDirect RDMA** so data moves directly from GPU memory across the network to remote GPU memory without touching the CPU or kernel.

The single highest-value check this skill performs: confirm NCCL actually selected the `efa` provider with RDMA transport. When EFA is misconfigured, NCCL silently falls back to TCP — training still runs, but ~100x slower and at ~100x the cost per token. Customers often do not notice until the bill arrives.

### Software Stack

```text
+--------------------------------------------------+
|  PyTorch / TensorFlow / Training & Inference     |   Application
+--------------------------------------------------+
|  NCCL (AllReduce, Broadcast, AllGather, etc.)    |   Collective comms
+--------------------------------------------------+
|  aws-ofi-nccl  (includes NCCL tuner plugin)      |   NCCL network plugin
+--------------------------------------------------+
|  Libfabric  (EFA provider)                       |   Fabric abstraction
+--------------------------------------------------+
|  ibverbs (rdma-core) - data ops, kernel bypass   |   User space
+--------------------------------------------------+
|  EFA kernel driver (efa.ko)                      |   Kernel space
+--------------------------------------------------+
|  AWS EFA NIC (Nitro)                             |   Hardware
+--------------------------------------------------+
```

### Why NUMA Topology Matters

P-family instances are divided into **NUMA domains**, each with its own CPUs, memory, and PCIe root complex. EFA devices are physically co-located with their paired GPUs on the same PCIe switch, which is what enables GPUDirect RDMA. All EFA interfaces **must** be attached at instance launch time — post-launch attachment is not supported. Missing EFA devices force NCCL into suboptimal NIC assignments, degrading collective bandwidth and raising training cost per token.

## Top 6 Root Causes

These six issues account for the large majority of EFA problems. The diagnostic ladder below maps each failing check to the matching root cause here.

### 1. Security Groups Not Configured

This is the single most common EFA misconfiguration. EFA traffic is **not** normal IP traffic. The security group attached to each EFA interface must allow **all traffic to and from its own security group ID** on both inbound and outbound:

| Direction | Type        | Protocol | Port Range | Source / Destination  |
| --------- | ----------- | -------- | ---------- | --------------------- |
| Inbound   | All traffic | All      | All        | Own Security Group ID |
| Outbound  | All traffic | All      | All        | Own Security Group ID |

### 2. Missing EFA Devices at Launch

All EFA interfaces must be specified in the `--network-interfaces` parameter of `run-instances` at launch time. Post-launch ENI attachment is **not supported** for EFA. Symptoms: degraded collective bandwidth, suboptimal NCCL ring formation, higher cost per token. Always validate the EFA device count before a production run.

### 3. Wrong Interface Type

| interfaceType | Description                       | Recommendation                         |
| ------------- | --------------------------------- | -------------------------------------- |
| `interface`   | ENA only (IP networking)          | Use for the primary interface only     |
| `efa-only`    | EFA capabilities only, no IP      | **Recommended** for all EFA interfaces |
| `efa`         | Both EFA and ENA on one interface | **Deprecated** — no longer recommended |

### 4. Instances Not in Same AZ and VPC

EFA traffic is not routable and cannot cross Availability Zones or VPCs. All instances communicating over EFA must be in the **same AZ and VPC**. Cross-subnet communication works only if the subnets share the same AZ ID.

### 5. Container Misconfiguration

These `docker run` flags are **required** for EFA workloads in containers:

| Flag                          | Purpose                                           |
| ----------------------------- | ------------------------------------------------- |
| `--network=host`              | Host network stack for NCCL/MPI bootstrap         |
| `--ipc=host`                  | Shared memory for intra-node GPU P2P (NCCL/CUDA)  |
| `--ulimit memlock=-1`         | Unlimited locked pinned memory for EFA/RDMA       |
| `--ulimit stack=67108864`     | 64 MB stack for multi-threaded NCCL/MPI workloads |
| `--device=/dev/infiniband/`   | RDMA device files for the EFA control path        |
| `--runtime nvidia --gpus all` | GPU access via the NVIDIA container toolkit       |

Missing any of these causes EFA/NCCL to fail silently or fall back to slower TCP paths.

### 6. Outdated NCCL Plugin in NGC Containers

Since aws-ofi-nccl v1.15.0 (EFA Installer 1.42.0), the NCCL network plugin library was renamed from `libnccl-net-aws-ofi.so` to `libnccl-net-ofi.so`. NVIDIA NGC containers may retain the old library in `/opt/amazon/aws-ofi-nccl/lib/`, causing NCCL to load an outdated version even after updating via the EFA installer.

```bash
rm -rf /opt/amazon/aws-ofi-nccl
ldconfig
```

## Diagnostic Ladder

Run these in order. Each rung has a **check command**, a **pass condition**, and the **fix** when it fails. Stop at the first failure, apply the fix, then re-run the NCCL transport check (rung 7) to confirm before continuing. The full versions of these checks are in `references/diagnostic-scripts.md`.

| # | Check                 | Command                                 | Fails when                           | Fix (root cause)                                                                                                                     |
| - | --------------------- | --------------------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| 1 | Same AZ + VPC         | compare placement of all nodes          | nodes differ in AZ/VPC               | Relaunch in one AZ + VPC. EFA is not routable across either (cause #4).                                                              |
| 2 | Security group        | `aws ec2 describe-security-group-rules` | no self-referencing all-traffic rule | Add inbound + outbound all-traffic rules to the SG's own ID (cause #1).                                                              |
| 3 | EFA devices visible   | `lspci \| grep -ci efa`                 | count < expected for the instance    | Were all interfaces attached at launch? Post-launch attach is unsupported — relaunch (cause #2).                                     |
| 4 | Kernel module         | `lsmod \| grep efa`                     | module not loaded                    | Install/reinstall via the EFA installer.                                                                                             |
| 5 | Libfabric provider    | `fi_info -p efa -t FI_EP_RDM`           | no `provider: efa`                   | Reinstall Libfabric; check `/etc/ld.so.conf.d/000_efa.conf`; run `ldconfig`.                                                         |
| 6 | Node-to-node fabric   | `fi_pingpong -p efa` (server + client)  | hangs or errors                      | Check routing tables, NACLs, host firewall; confirm cross-subnet shares the same AZ ID.                                              |
| 7 | NCCL selects EFA      | `NCCL_DEBUG=INFO` in the workload       | `NET/Socket` or `provider is tcp`    | Check the aws-ofi-nccl plugin (`ldconfig -p \| grep nccl`), NGC stale-plugin issue (cause #6), container userspace stack (cause #5). |
| 8 | Bandwidth at baseline | `all_reduce_perf` from nccl-tests       | busbw well below baseline            | Check NUMA topology, missing devices, GPU placement, tuner plugin.                                                                   |
| 9 | Escalate              | gather evidence bundle                  | all above pass, BW still low         | Open an AWS Support case (template in `references/diagnostic-scripts.md`).                                                           |

For a multi-node hang where single-node works, jump straight to rung 7 — it is almost always a TCP fallback (the EFA userspace stack is missing or not on the loader path), not a hardware fault.

## NCCL Verification

This is the highest-value check in the skill: confirm NCCL actually selected EFA with RDMA transport, not the TCP/Socket fallback. Enable debug before launch:

```bash
export NCCL_DEBUG=INFO
export NCCL_DEBUG_SUBSYS=INIT,NET   # focus output on init + network selection
```

Healthy EFA — these lines appear:

```text
NCCL INFO NET/Plugin: Loaded net plugin Libfabric (v11)
NCCL INFO NET/OFI Initializing aws-ofi-nccl 1.17.2
NCCL INFO NET/OFI Selected provider is efa, fabric is efa-direct (found 32 nics)
NCCL INFO NET/OFI Using transport protocol RDMA (platform set)
NCCL INFO TUNER/Plugin: Using nccl_ofi_tuner (v3)
```

Broken — TCP fallback (the canonical "20x slower on multi-node" failure):

```text
NCCL INFO NET/Socket : Using network Socket
```

When you see `NET/Socket`, NCCL never loaded the EFA path. In real incidents this comes from the EFA userspace stack (Libfabric + aws-ofi-nccl) missing inside a container even though `/dev/infiniband/uverbs*` was passed through — a single-node job looks fine while the 2-node job runs ~20x slower. Fix the container image (cause #5), not the application.

### Red Flags

| Symptom in NCCL_DEBUG output                            | Likely cause                                                                               |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `NET/Socket : Using network Socket`                     | EFA never loaded; pure TCP fallback. Missing userspace stack or plugin not on loader path. |
| `Selected provider is tcp` instead of `efa`             | EFA devices not visible; fell back to TCP. Check device count.                             |
| `Using transport protocol SENDRECV` instead of `RDMA`   | GPUDirect RDMA not active. Check EFA provider and visibility.                              |
| `found 8 nics` on p5.48xlarge (expected 32)             | Missing EFA interfaces. Relaunch with all interfaces.                                      |
| No tuner plugin loaded                                  | aws-ofi-nccl outdated or missing. Reinstall via EFA installer.                             |
| Inter-node channels show `NET/Libfabric` without GDRDMA | GPUDirect RDMA not active inter-node. Check topology.                                      |

### Expected nccl-tests Benchmarks (p5.48xlarge baseline)

| Configuration                        | Test            | Avg Bus BW | Peak Bus BW |
| ------------------------------------ | --------------- | ---------- | ----------- |
| 1x p5.48xlarge (8 GPUs, single-node) | all_reduce_perf | ~109 GB/s  | ~445 GB/s   |
| 2x p5.48xlarge (16 GPUs, multi-node) | all_reduce_perf | ~129 GB/s  | ~487 GB/s   |
| 2x p5.48xlarge, `FI_PROVIDER=tcp`    | all_reduce_perf | ~1.13 GB/s | ~2.23 GB/s  |

The TCP fallback row demonstrates the ~114x performance difference versus EFA/RDMA — and why confirming the `efa` provider is the most important check in this skill.

## Gotchas

- **`fi_info: command not found` does not mean EFA is broken.** It is usually just a PATH issue (the binary lives in `/opt/amazon/efa/bin`). Confirm the transport from NCCL logs (`NET/OFI` vs `NET/Socket`) before concluding the stack is missing.
- **Single-node fast, multi-node slow is the TCP-fallback fingerprint.** Intra-node uses NVLink and hides a broken fabric; the regression only appears once traffic must cross EFA. Always test multi-node before declaring success.
- **A passed-through device is not a working stack.** `/dev/infiniband/uverbs*` existing inside a container only means the _device_ is mapped. NCCL still falls back to TCP unless Libfabric + aws-ofi-nccl + rdma-core userspace libs are installed and on the loader path.
- **NGC containers can ship a stale plugin.** Even after updating the EFA installer, NGC images may keep the old `libnccl-net-aws-ofi.so`. Remove `/opt/amazon/aws-ofi-nccl` and re-run `ldconfig` (cause #6).
- **AWS Batch / orchestrators can silently drop the device mapping.** If a containerized job regresses to `NET/Socket`, check the job definition still maps `/dev/infiniband` with `READ|WRITE|MKNOD` permissions.
- **Pin the EFA installer version.** Container builds break when the installer pulls different dependencies across versions. Pin `EFA_VERSION` and install deps (hwloc, libevent, rdma userspace) up front.
- **`fi_pingpong` isolates infra from software.** If it hangs, the problem is below NCCL (security group, routing, AZ) — do not waste time debugging the ML stack.

## Output Format

For each diagnosis, report:

1. **Symptom** — what the builder observed (hang, slow step time, low busbw, error).
2. **Root Cause** — which layer failed and which of the 6 root causes it maps to.
3. **Evidence** — the specific command output that confirms it (NCCL transport line, `lspci` count vs expected, SG rule check, `fi_info` result).
4. **Fix** — the exact command or config change to apply.
5. **Verification** — re-run `NCCL_DEBUG=INFO` (expect `Selected provider is efa` / `RDMA`) and `all_reduce_perf`; report measured busbw vs the baseline.
6. **Prevention** — guardrail to catch it earlier (pin installer, bake the stack into the AMI/image, add a pre-run `nccl-tests` gate).

## Reference Files

- `references/diagnostic-scripts.md` — copy-paste bash scripts (EFA health check, security group validator, device count validator, container readiness check, `fi_pingpong` test) and the AWS Support escalation template.
- `references/instance-reference.md` — P-family EFA device counts and recommended interface configuration, plus the EFA installer command and flag reference.

## Related Skills

- `networking` — VPC, subnet, and security group fundamentals that EFA depends on
- `ec2` — P-family instance selection, placement groups, launch templates
- `eks` — running EFA workloads on Kubernetes with the EFA device plugin
- `mlops` — distributed training architecture and SageMaker HyperPod
- `observability` — capturing NCCL and training throughput metrics

## Anti-Patterns

- **Attaching EFA interfaces after launch**: not supported. All EFA interfaces must be present at `run-instances` time, or you must terminate and relaunch.
- **Leaving NCCL on the TCP fallback**: a working-but-slow job that never selected the `efa` provider wastes ~100x on data transfer. Always grep `NCCL_DEBUG=INFO` for `Selected provider is efa`.
- **Default security group on EFA interfaces**: without a self-referencing all-traffic rule, EFA traffic is dropped. The job may still bootstrap over TCP and hide the problem.
- **Spreading distributed nodes across AZs**: EFA cannot cross AZ boundaries. Use a single AZ and a cluster placement group.
- **Using `interfaceType=efa`**: deprecated. Use `efa-only` for EFA interfaces and `interface` for the primary ENA interface only.
- **Skipping `nccl-tests` before a production run**: a five-minute all_reduce_perf check catches missing devices and topology problems before a multi-day training job burns budget on them.
