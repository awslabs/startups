# EFA Instance & Installer Reference

## Instance Networking Quick Reference

P-family EFA-supported instance types, expected EFA device counts, and the recommended network interface configuration to maximize EFA bandwidth while minimizing IP address consumption. Verify counts against current AWS documentation — new instance types are added regularly and bandwidth figures change.

| Instance           | GPUs | GPU Type    | Max EFA | EFA:GPU | BW/EFA (Gbps) | Total EFA BW (Gbps) |
| ------------------ | ---- | ----------- | ------- | ------- | ------------- | ------------------- |
| p4d.24xlarge       | 8    | A100 80GB   | 4       | 1:2     | 100           | 400                 |
| p5.48xlarge        | 8    | H100 80GB   | 32      | 4:1     | 100           | 3,200               |
| p5e.48xlarge       | 8    | H200 141GB  | 32      | 4:1     | 100           | 3,200               |
| p5en.48xlarge      | 8    | H200 141GB  | 16      | 2:1     | 200           | 3,200               |
| p6-b200.48xlarge   | 8    | B200 180GB  | 8       | 1:1     | 400           | 3,200               |
| p6e-gb200.36xlarge | 4    | GB200 185GB | 8       | 2:1     | 400           | 1,600               |

On p6e-gb200, each GPU has two co-located EFA NICs that share 400 Gbps. The optimal config uses 4 of the 8 EFA interfaces (one per GPU pair) to reach the full 1,600 Gbps.

### Interface Configuration Rules

- The primary interface (NetworkCardIndex 0, DeviceIndex 0) **must** be `interfaceType=interface` (ENA).
- All additional EFA interfaces should use `interfaceType=efa-only`.
- The primary ENI must be on NetworkCardIndex 0 (NCI0) and DeviceIndex 0 (DI0).
- An `efa-only` interface and an ENA interface on the same network card share bandwidth.

Reference: [EFA-supported accelerated instance types](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/efa-acc-inst-types.html)

## EFA Installer Reference

The EFA Installer is a self-contained package that installs the EFA kernel module (`efa.ko`), Libfabric, aws-ofi-nccl, OpenMPI (optional), and rdma-core. Set `EFA_VERSION` to the current release; check the AWS documentation for the latest.

### Installation Commands

Standard install (bare metal / VM host):

```bash
export EFA_VERSION=1.47.0
curl -O https://efa-installer.amazonaws.com/aws-efa-installer-${EFA_VERSION}.tar.gz
tar -xf aws-efa-installer-${EFA_VERSION}.tar.gz
cd aws-efa-installer
sudo ./efa_installer.sh
```

Container image install:

```bash
sudo ./efa_installer.sh -y --skip-kmod --skip-limit-conf --no-verify
```

Host-only install (Kubernetes node / container host):

```bash
sudo ./efa_installer.sh -y --minimal
```

### Dockerfile Snippet

```dockerfile
ARG EFA_VERSION=1.47.0

RUN mkdir -p /tmp/efa && \
    cd /tmp/efa && \
    curl --retry 3 --retry-delay 2 -fsSL -o aws-efa-installer-${EFA_VERSION}.tar.gz \
        https://efa-installer.amazonaws.com/aws-efa-installer-${EFA_VERSION}.tar.gz && \
    tar -xf aws-efa-installer-${EFA_VERSION}.tar.gz && \
    cd aws-efa-installer && \
    ./efa_installer.sh -y --skip-kmod --skip-limit-conf --no-verify && \
    rm -rf /tmp/efa && \
    ldconfig

# Append Libfabric tools (e.g. fi_info) to PATH
ENV PATH=/opt/amazon/efa/bin:$PATH
```

### Installer Flags

| Flag                | Short | Description                                               |
| ------------------- | ----- | --------------------------------------------------------- |
| `--skip-kmod`       | `-k`  | Skip kernel module install (handled by the host)          |
| `--skip-limit-conf` | `-l`  | Skip ulimit configuration (handled by container runtime)  |
| `--no-verify`       | `-n`  | Skip EFA device verification (for container image builds) |
| `--minimal`         | `-m`  | Only install kernel driver + rdma-core (container hosts)  |
| `--yes`             | `-y`  | Non-interactive mode                                      |

## See Also

- [EC2 EFA User Guide](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/efa.html)
- [EFA-supported accelerated instance types](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/efa-acc-inst-types.html)
- [EC2 Instance Topology API](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-topology.html)
- [nccl-tests (GitHub)](https://github.com/NVIDIA/nccl-tests)
- [AWS Deep Learning AMIs](https://docs.aws.amazon.com/dlami/)
- [AWS Deep Learning Containers](https://aws.github.io/deep-learning-containers/)
- [SRD — A Cloud-Optimized Transport Protocol](https://aws.amazon.com/srd/)
