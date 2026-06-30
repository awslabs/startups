# EFA Diagnostic Scripts

Copy-paste these scripts to run on customer instances. Each targets a specific layer of the EFA stack. Run them in order; stop at the first failure and fix it before continuing.

## EFA Health Check

Produces a full snapshot of EFA stack status on a single instance.

```bash
#!/bin/bash
# EFA Health Check Script
# Usage: Run on each instance to validate the EFA stack

echo "============================================"
echo "EFA HEALTH CHECK"
echo "============================================"

# 1. Instance type
echo "--- Instance Type ---"
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
INSTANCE_TYPE=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/instance-type)
echo "Instance type: $INSTANCE_TYPE"

# 2. EFA kernel module
echo "--- EFA Kernel Module ---"
if lsmod | grep -q efa; then
    echo "PASS: EFA module is loaded"
    modinfo efa 2>/dev/null | grep -E "^(version|filename|description):"
else
    echo "FAIL: EFA module is NOT loaded"
    echo "  Action: Install the EFA driver using the EFA Installer"
fi

# 3. EFA device count (PCIe)
echo "--- EFA Devices (PCIe) ---"
EFA_COUNT=$(lspci | grep -ci efa)
echo "EFA devices found: $EFA_COUNT"

# 4. RDMA devices
echo "--- RDMA Devices ---"
if command -v ibv_devices &> /dev/null; then
    RDMA_COUNT=$(ibv_devices | tail -n +3 | wc -l)
    echo "RDMA devices found: $RDMA_COUNT"
    ibv_devices
else
    echo "FAIL: ibv_devices not found. Install rdma-core."
fi

# 5. Libfabric EFA provider
echo "--- Libfabric EFA Provider ---"
if command -v fi_info &> /dev/null; then
    FI_OUTPUT=$(fi_info -p efa -t FI_EP_RDM 2>&1)
    if echo "$FI_OUTPUT" | grep -q "provider: efa"; then
        echo "PASS: EFA provider available"
        echo "$FI_OUTPUT" | head -8
    else
        echo "FAIL: EFA provider NOT found in fi_info"
        echo "  Action: Check the Libfabric installation"
    fi
else
    echo "FAIL: fi_info not found. Install Libfabric via the EFA Installer."
fi

# 6. Library linkage
echo "--- Library Linkage ---"
echo "Linker config files:"
ls /etc/ld.so.conf.d/ 2>/dev/null | grep -E "efa|ofinccl"
echo "Linked libraries:"
ldconfig -p 2>/dev/null | grep -E "libfabric|libnccl-net|libnccl-ofi|ofi"

# 7. EFA software paths
echo "--- EFA Software Paths ---"
echo "Libfabric: $(ls /opt/amazon/efa/lib64/ 2>/dev/null || echo 'not found')"
echo "aws-ofi-nccl: $(ls /opt/amazon/ofi-nccl/lib64/ 2>/dev/null || echo 'not found')"

echo "============================================"
echo "EFA HEALTH CHECK COMPLETE"
echo "============================================"
```

## Security Group Validator

Validates that the security groups on the instance have the self-referencing all-traffic rules EFA requires. Requires the AWS CLI and `jq`, and read access to `ec2:DescribeInstances` and `ec2:DescribeSecurityGroupRules`.

```bash
#!/bin/bash
# EFA Security Group Validator
# Usage: Run on the instance, or locally with appropriate IAM permissions

TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
INSTANCE_ID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/instance-id)
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/placement/region)

echo "Instance: $INSTANCE_ID ($REGION)"

SG_IDS=$(aws ec2 describe-instances \
  --instance-ids "$INSTANCE_ID" \
  --region "$REGION" \
  --query 'Reservations[].Instances[].NetworkInterfaces[].Groups[].GroupId' \
  --output text | tr '\t' '\n' | sort -u)

for SG_ID in $SG_IDS; do
    echo "--- Checking Security Group: $SG_ID ---"

    INBOUND_SELF=$(aws ec2 describe-security-group-rules \
      --region "$REGION" \
      --filters "Name=group-id,Values=$SG_ID" \
      --query "SecurityGroupRules[?IsEgress==\`false\` && IpProtocol==\`-1\` && ReferencedGroupInfo.GroupId==\`$SG_ID\`]" \
      --output json | jq length)

    if [ "$INBOUND_SELF" -gt 0 ]; then
        echo "  Inbound: PASS (self-referencing all-traffic rule found)"
    else
        echo "  Inbound: FAIL - add inbound rule: All traffic, All ports, Source = $SG_ID"
    fi

    OUTBOUND_SELF=$(aws ec2 describe-security-group-rules \
      --region "$REGION" \
      --filters "Name=group-id,Values=$SG_ID" \
      --query "SecurityGroupRules[?IsEgress==\`true\` && IpProtocol==\`-1\` && ReferencedGroupInfo.GroupId==\`$SG_ID\`]" \
      --output json | jq length)

    if [ "$OUTBOUND_SELF" -gt 0 ]; then
        echo "  Outbound: PASS (self-referencing all-traffic rule found)"
    else
        echo "  Outbound: FAIL - add outbound rule: All traffic, All ports, Destination = $SG_ID"
    fi
done
```

## EFA Device Count Validator

Compares the actual number of EFA PCIe devices against the expected count for the instance type. Verify the expected counts against current AWS documentation, since new instance types are added regularly.

```bash
#!/bin/bash
# EFA Device Count Validator
# Usage: Run on the instance

TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
INSTANCE_TYPE=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/instance-type)

declare -A EXPECTED_EFA
EXPECTED_EFA[p4d.24xlarge]=4
EXPECTED_EFA[p5.4xlarge]=1
EXPECTED_EFA[p5.48xlarge]=32
EXPECTED_EFA[p5e.48xlarge]=32
EXPECTED_EFA[p5en.48xlarge]=16
EXPECTED_EFA[p6-b200.48xlarge]=8
EXPECTED_EFA[p6e-gb200.36xlarge]=8

ACTUAL_EFA=$(lspci | grep -ci efa)
EXPECTED=${EXPECTED_EFA[$INSTANCE_TYPE]:-"unknown"}

echo "Instance type:        $INSTANCE_TYPE"
echo "EFA devices found:    $ACTUAL_EFA"
echo "EFA devices expected: $EXPECTED"

if [ "$EXPECTED" = "unknown" ]; then
    echo "WARNING: Instance type not in reference table. Verify manually."
elif [ "$ACTUAL_EFA" -eq "$EXPECTED" ]; then
    echo "PASS: EFA device count matches expected."
else
    echo "FAIL: Expected $EXPECTED EFA devices but found $ACTUAL_EFA"
    echo "  Likely cause: not all EFA interfaces were attached at launch."
    echo "  Action: terminate and relaunch with all EFA interfaces attached."
    echo "  Note: post-launch attachment of EFA interfaces is NOT supported."
fi
```

## Container EFA Readiness Check

Run **inside** the container to verify EFA devices, ulimits, and the network namespace are correctly exposed.

```bash
#!/bin/bash
# Container EFA Readiness Check
# Usage: Run INSIDE the container

echo "--- /dev/infiniband ---"
if [ -d /dev/infiniband ]; then
    UVERBS_COUNT=$(ls /dev/infiniband/uverbs* 2>/dev/null | wc -l)
    echo "PASS: /dev/infiniband is mounted ($UVERBS_COUNT uverbs devices)"
else
    echo "FAIL: /dev/infiniband is NOT mounted"
    echo "  Action: add --device=/dev/infiniband/ to docker run"
fi

echo "--- Ulimit memlock ---"
MEMLOCK=$(ulimit -l)
if [ "$MEMLOCK" = "unlimited" ]; then
    echo "PASS: memlock is unlimited"
else
    echo "FAIL: memlock is $MEMLOCK (should be unlimited)"
    echo "  Action: add --ulimit memlock=-1 to docker run"
fi

echo "--- Ulimit stack ---"
STACK=$(ulimit -s)
if [ "$STACK" -ge 65536 ] 2>/dev/null; then
    echo "PASS: stack size is sufficient ($STACK)"
else
    echo "WARNING: stack may be too small ($STACK). Recommend --ulimit stack=67108864"
fi

echo "--- EFA in container ---"
if command -v fi_info &> /dev/null; then
    EFA_PROVIDERS=$(fi_info -p efa -t FI_EP_RDM 2>&1 | grep -c "provider: efa")
    echo "EFA providers visible: $EFA_PROVIDERS"
else
    echo "fi_info not found in container. Install Libfabric in the container image."
fi

echo "--- GPUs ---"
if command -v nvidia-smi &> /dev/null; then
    GPU_COUNT=$(nvidia-smi --query-gpu=count --format=csv,noheader | head -1)
    echo "GPUs visible: $GPU_COUNT"
else
    echo "nvidia-smi not found"
fi
```

## fi_pingpong Quick Network Test

Validates basic EFA connectivity between two instances. If this hangs or fails, the problem is at the infrastructure level (security groups, routing, AZ mismatch) — not in the ML stack.

```bash
# On the server instance (listens on port 47592 by default):
fi_pingpong -p efa

# On the client instance:
fi_pingpong -p efa <server_instance_private_ip>
```

Expected output is a table of increasing message sizes (64 bytes through several KB) with rising MB/sec throughput. A hang means traffic is being dropped before it reaches the EFA provider.

## Quick NCCL Transport Check

The fastest single check: print device + plugin state at job startup (before `torchrun`), then confirm the transport NCCL actually selected. Run this inside the container/node where the workload runs.

```bash
# Devices should exist (device pass-through into the container)
ls -l /dev/infiniband/uverbs* 2>/dev/null | head

# Plugin + libfabric should be visible to the dynamic linker
ldconfig -p | grep -E 'libnccl-net|libfabric' || echo "MISSING: EFA userspace not on loader path"

# Turn on the signal you actually care about
export NCCL_DEBUG=INFO
export NCCL_DEBUG_SUBSYS=INIT,NET
```

Then read the workload's NCCL output:

- Good: `NET/OFI ... Selected provider is efa` and `Using transport protocol RDMA`
- Bad: `NET/Socket : Using network Socket` (TCP fallback — EFA userspace missing or not on the loader path)

If a containerized job regresses to `NET/Socket` after previously working, check that the orchestrator (e.g. AWS Batch job definition) still maps `/dev/infiniband` with `READ|WRITE|MKNOD` permissions, and that the aws-ofi-nccl plugin is still resolvable via `ldconfig -p`.

## AWS Support Escalation Template

When all debugging steps are exhausted, open an AWS Support case. Include the following to minimize back-and-forth:

```text
1. INSTANCE DETAILS
   - Instance IDs:
   - Instance type:
   - Region / AZ:
   - AMI ID:
   - Placement group (if any):

2. NETWORK CONFIGURATION
   - Interface types used (efa-only / interface / efa):
   - Number of EFA interfaces attached:
   - Security group IDs:
   - VPC ID / Subnet IDs:

3. SOFTWARE VERSIONS
   - EFA Installer version:
   - EFA driver version (modinfo efa | grep version):
   - Libfabric version (fi_info -p efa | grep version):
   - aws-ofi-nccl version:
   - NCCL version:
   - CUDA version:
   - Container image (if applicable):

4. DIAGNOSTIC OUTPUT (attach as files)
   - Full output of the EFA Health Check script
   - Full output of: lspci | grep -i efa
   - Full output of: ibv_devices
   - Full output of: fi_info -p efa -t FI_EP_RDM
   - Full NCCL_DEBUG=INFO logs from the failing workload
   - nccl-tests results (if available)

5. PROBLEM DESCRIPTION
   - What the workload is trying to do:
   - Error / behavior observed:
   - When it started:
   - Steps to reproduce:

6. WHAT HAS BEEN TRIED
   - (List debugging steps already completed from this skill)
```
