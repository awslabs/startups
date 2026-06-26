# Graviton Cost Optimization Reference

Reference document for integrating Graviton migration recommendations into the migration plugin's Design and Estimate phases. Intended to be condensed into `references/shared/graviton.md` for conditional loading.

---

## 1. How Graviton Saves Money

### Two distinct savings mechanisms (keep separate in user-facing output)

| Mechanism                                             | Magnitude                                        | Modelable in Estimate?     | Notes                                |
| ----------------------------------------------------- | ------------------------------------------------ | -------------------------- | ------------------------------------ |
| **Instance-hour price discount**                      | 15–20% lower per hour vs x86 at same vCPU/memory | ✅ Yes — use pricing API   | Reliable, consistent across families |
| **Performance uplift** (may reduce required capacity) | Varies; up to 25% more throughput per vCPU       | ❌ No — workload-dependent | Only claimable after benchmarking    |

**Rule for the plugin:** Estimate phase models ONLY the hourly price discount. Performance uplift is mentioned in Design narrative ("validate with load test; you may be able to downsize further") but NOT counted in automated savings math.

**Why vCPU ≠ capacity:** Graviton vCPUs are physical cores; x86 vCPUs are typically hyperthreaded logical cores. A 4-vCPU Graviton instance may outperform a 4-vCPU x86 instance on CPU-bound work. The GCP→AWS mapping table (§3) provides a _starting point_; right-sizing requires benchmarking.

### Verified instance-hour savings by family

| Graviton instance | x86 equivalent | vCPU | Memory | Hourly savings |
| ----------------- | -------------- | ---- | ------ | -------------- |
| t4g.xlarge        | t3.xlarge      | 4    | 16 GB  | 19.2%          |
| c7g.4xlarge       | c6i.4xlarge    | 16   | 32 GB  | 15.0%          |
| m7g.xlarge        | m7i.xlarge     | 4    | 16 GB  | ~20%           |
| r7g.xlarge        | r7i.xlarge     | 4    | 32 GB  | ~20%           |

Source: [AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/optimize-costs-microsoft-workloads/net-graviton.html)

### Customer evidence (for narrative/docs only, NOT automated math)

| Customer  | Result                        | Workload        |
| --------- | ----------------------------- | --------------- |
| Pinterest | 47% cost savings              | Web/analytics   |
| SAP       | 35% better price-performance  | Enterprise apps |
| Sprinklr  | 25% cost reduction            | SaaS platform   |
| Typeform  | 19% cost + 40% less CPU usage | EKS containers  |

---

## 2. Graviton Compatibility Decision Matrix

### By language/runtime

| Workload type                         | Tier         | Migration effort | Notes                                                                                                                          |
| ------------------------------------- | ------------ | ---------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Python app (containers/Lambda)        | ready        | Very low         | Most packages ship arm64 wheels                                                                                                |
| Node.js app (containers/Lambda)       | ready        | Very low         | V8 is arm64-native                                                                                                             |
| Java app (pure JVM, Corretto/OpenJDK) | ready        | Very low         | Zero code changes                                                                                                              |
| Go app (compiled)                     | ready        | Very low         | `GOARCH=arm64` recompile                                                                                                       |
| PHP app                               | ready        | Very low         | PHP runtime supports arm64                                                                                                     |
| Ruby app                              | ready        | Low              | Most gems have arm64 support; verify native extensions                                                                         |
| .NET on Linux (.NET 6+)               | ready        | Low              | arm64 natively supported                                                                                                       |
| Rust (compiled, no x86 asm)           | ready        | Low              | Cross-compile or build on arm64                                                                                                |
| Java with JNI dependencies            | conditional  | Low–Medium       | Need to verify arm64 native builds exist                                                                                       |
| Python with niche C extensions        | conditional  | Low–Medium       | numpy/pandas fine; niche packages may lack arm64                                                                               |
| C/C++ (no x86 assembly)               | conditional  | Medium           | Recompile required                                                                                                             |
| C/C++ with SSE/AVX/x86 intrinsics     | conditional  | High             | Needs ARM NEON port                                                                                                            |
| GPU / CUDA workloads                  | incompatible | N/A              | Route to G5/G6 instances, not Graviton                                                                                         |
| Windows / .NET Framework              | incompatible | N/A              | Graviton = Linux only                                                                                                          |
| RDS Oracle                            | conditional  | Low              | Supported on some versions; check [docs](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.DBInstanceClass.html) |
| RDS SQL Server                        | incompatible | N/A              | Not supported on Graviton                                                                                                      |
| Proprietary/vendor AMIs               | conditional  | Unknown          | Depends on vendor arm64 support                                                                                                |
| Closed-source agents/binaries         | conditional  | Unknown          | Contact vendor for arm64 availability                                                                                          |

### By discovery path

| Discovery input            | What's detectable                              | Default tier                                |
| -------------------------- | ---------------------------------------------- | ------------------------------------------- |
| **App code + Dockerfiles** | Language, native deps, SIMD usage, base images | Full tier assignment                        |
| **IaC only (Terraform)**   | machine_type, node_selector, Cloud Run cpu     | conditional (at best)                       |
| **Billing only**           | Service usage, no architecture signals         | Managed DB/cache → ready; compute → unknown |

---

## 3. GCP-to-AWS Instance Mapping (Starting Point)

**Important:** These are nominal vCPU/memory matches, not capacity guarantees. Graviton physical cores often outperform hyperthreaded x86 vCPUs. Validate sizing with load testing after migration.

| GCP machine type | AWS x86 equivalent | AWS Graviton equivalent | Hourly savings vs x86 |
| ---------------- | ------------------ | ----------------------- | --------------------- |
| e2-standard-4    | m6i.xlarge         | m7g.xlarge              | ~20%                  |
| e2-standard-8    | m6i.2xlarge        | m7g.2xlarge             | ~20%                  |
| n2-standard-4    | m6i.xlarge         | m7g.xlarge              | ~20%                  |
| c2-standard-8    | c6i.2xlarge        | c7g.2xlarge             | ~15%                  |
| n2-highmem-4     | r6i.xlarge         | r7g.xlarge              | ~20%                  |
| e2-micro/small   | t3.micro/small     | t4g.micro/small         | ~19%                  |

---

## 4. Managed Services — Instance Family Swap Only

| Service                                 | Graviton instance family  | Effort                  | Notes                           |
| --------------------------------------- | ------------------------- | ----------------------- | ------------------------------- |
| Amazon RDS (MySQL, PostgreSQL, MariaDB) | db.m7g, db.r7g, db.t4g    | Instance type change    | ✅ Fully supported              |
| Amazon RDS (Oracle)                     | db.m7g (some versions)    | Instance type change    | ⚠️ Check version compatibility   |
| Amazon RDS (SQL Server)                 | —                         | N/A                     | ❌ Not supported on Graviton    |
| Amazon Aurora                           | db.r7g, db.r6g            | Instance type change    | ✅ Fully supported              |
| Amazon ElastiCache                      | cache.m7g, cache.r7g      | Node type change        | ✅ Fully supported              |
| Amazon OpenSearch                       | m7g, r7g, c7g             | Instance type change    | ✅ Fully supported              |
| Amazon MSK                              | kafka.m7g                 | Broker type change      | ✅ Fully supported              |
| Amazon EKS / ECS (EC2)                  | m7g, c7g, r7g node groups | Node group config       | arm64 container images required |
| ECS Fargate                             | ARM64 platform version    | runtimePlatform setting | ✅ ~20% cheaper                 |
| AWS Lambda                              | arm64 architecture        | One config toggle       | ✅ ~20% cheaper per GB-second   |
| Amazon EMR Serverless                   | arm64 architecture option | Application setting     | ✅ Better price-performance     |

---

## 5. Detection Signals for the Plugin

### Discover phase — app code path

| Signal                             | Where to find it                                                        | Indicates                            |
| ---------------------------------- | ----------------------------------------------------------------------- | ------------------------------------ |
| Language runtime                   | package.json, requirements.txt, go.mod, pom.xml, Gemfile, composer.json | Compatibility tier                   |
| Dockerfile `FROM` base image       | Dockerfile                                                              | Whether multi-arch base is available |
| `platform: linux/amd64` in compose | docker-compose.yml                                                      | Hardcoded x86 — needs change         |
| Native C extensions                | requirements.txt (numpy, etc.), package.json (node-gyp)                 | Potential arm64 gap                  |
| x86 assembly/intrinsics            | `grep -rE "**asm**                                                      | _mm_                                 |
| JNI libraries                      | `grep -rE "System\.loadLibrary\|JNI_OnLoad"` in Java                    | Need arm64 native builds             |
| CUDA / GPU usage                   | `grep -rE "import cuda\|torch\.cuda\|nvidia\|gpu"`                      | Not Graviton → route to G5/G6        |

### Discover phase — IaC-only path

| Signal                    | Where to find it                   | Indicates                       |
| ------------------------- | ---------------------------------- | ------------------------------- |
| GCP `machine_type`        | Terraform google_compute_instance  | Map to Graviton equivalent      |
| `node_selector` with arch | Kubernetes manifests               | Current architecture constraint |
| Cloud Run CPU setting     | Terraform google_cloud_run_service | Map to Fargate ARM64            |
| Windows AMI               | Terraform AMI data source          | Graviton incompatible           |
| `.csproj` targeting net48 | .NET project files                 | .NET Framework → incompatible   |

### Discover phase — billing-only path

| Service in billing       | Default tier | Rationale                                              |
| ------------------------ | ------------ | ------------------------------------------------------ |
| Cloud SQL / managed DB   | ready        | All major managed DB engines support Graviton          |
| Memorystore / cache      | ready        | ElastiCache supports Graviton                          |
| Compute Engine (generic) | unknown      | Cannot determine language/deps from billing alone      |
| GKE                      | unknown      | Container arch unclear without manifests               |
| Cloud Run                | conditional  | Likely container-based, but can't confirm arm64 compat |

---

## 6. Integration into Plugin Phases

### Discover phase

- Emit `graviton_profile` per service with fields: `tier` (ready/conditional/incompatible/unknown), `signals[]`, `caveats[]`
- Populate from app code, IaC, or billing signals per §5
- GPU workloads: set tier=incompatible, add caveat "route to G5/G6"

### Clarify phase

**Default-when-compatible rule:** If ALL services have tier=ready, skip the Graviton question and default to Graviton (matches existing db.t4g defaults). Only ask when any service is tier=conditional with high-risk signals.

When asking:

> **Q: Some of your services have potential ARM64 compatibility considerations. Would you like to target Graviton (ARM64) instances for eligible services?**
> Graviton instances are 15–20% cheaper per hour. Your [language] workloads appear compatible; [service X] has [caveat].
> Options: Yes for all eligible (recommended) / No (stay on x86) / Let me decide per-service

### Design phase

- When Graviton selected (user or default): use Graviton instance types in all mappings
- When tier=conditional: note caveats in Design output, suggest "validate after migration"
- For containers: recommend **arm64-only** builds by default; multi-arch only when user chose "decide per-service" or has x86 holdouts
- For Lambda: set architecture to arm64
- For managed services: select Graviton instance families
- For EKS/ECS on dev tier: single-arch Graviton node group or Fargate ARM64 only (no mixed-cluster taints)
- For EKS/ECS on prod tier: note mixed-cluster option in runbook as optional module

Output in `aws-design.json` per service:

```json
"graviton": {
  "compatibility": "ready",
  "target_architecture": "arm64",
  "caveats": []
}
```

### Estimate phase

- When Graviton selected: Balanced tier uses Graviton instance pricing
- Add `architecture_comparison` block showing x86 equivalent monthly cost + delta:

```json
"architecture_comparison": {
  "graviton_monthly": 245.00,
  "x86_equivalent_monthly": 298.00,
  "savings_amount": 53.00,
  "savings_percent": 17.8,
  "note": "Hourly price savings only; performance uplift may allow further downsizing after load testing"
}
```

- Do NOT add Graviton as a fourth pricing tier — it's the architecture within Balanced/Premium/Optimized
- Model only the hourly price discount; do NOT model capacity reduction from performance uplift

### Generate phase

- Terraform: emit Graviton instance types (`instance_type = "m7g.xlarge"`)
- ECS Fargate: `runtimePlatform { cpuArchitecture = "ARM64", operatingSystemFamily = "LINUX" }`
- Lambda: `architectures = ["arm64"]`
- EKS: node group with arm64 AMI, single-arch (dev); optional mixed-cluster module reference (prod)
- Docker: emit `docker build --platform linux/arm64` in runbook (NOT multi-arch by default)
- Include "Graviton Migration Notes" section in output docs:
  - Services migrated to arm64
  - Any conditional-tier services with caveats
  - Recommendation to validate with load test post-migration

---

## 7. Pricing Data Requirements

### Rows needed in pricing-cache.md

| Service               | Architecture | Rate type                   | Required? |
| --------------------- | ------------ | --------------------------- | --------- |
| EC2 t4g family        | arm64        | per-hour by size            | ✅ Yes    |
| EC2 m7g family        | arm64        | per-hour by size            | ✅ Yes    |
| EC2 c7g family        | arm64        | per-hour by size            | ✅ Yes    |
| EC2 r7g family        | arm64        | per-hour by size            | ✅ Yes    |
| ECS Fargate ARM64     | arm64        | per-vCPU-hour + per-GB-hour | ✅ Yes    |
| Lambda arm64          | arm64        | per-GB-second + per-request | ✅ Yes    |
| RDS db.m7g / db.r7g   | arm64        | per-hour by size + engine   | ✅ Yes    |
| ElastiCache cache.m7g | arm64        | per-hour by size            | ✅ Yes    |

### Key pricing facts (for fallback when live API unavailable)

- EC2 Graviton: ~15–20% cheaper per hour vs same-spec x86
- Lambda arm64: ~20% cheaper per GB-second vs x86
- Fargate ARM64: ~20% cheaper per vCPU-hour and per-GB-hour vs x86
- All Graviton instances are eligible for Savings Plans and Reserved Instances

### Data sources

| Source                                                                                                   | Use                            | Freshness         |
| -------------------------------------------------------------------------------------------------------- | ------------------------------ | ----------------- |
| AWS Pricing API (`GetProducts`)                                                                          | Authoritative instance pricing | Real-time         |
| [EC2 pricing JSON](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/index.json) | Bulk pricing data              | Updated regularly |
| pricing-cache.md (plugin)                                                                                | Fallback when API unavailable  | Manual updates    |

---

## 8. Recommendation Rules

### Default to Graviton (no Clarify question) when:

- ALL services in inventory have tier=ready
- Workload is Python, Node.js, Go, PHP, Ruby, or Java (pure JVM) in containers
- Target is a managed service with Graviton support (RDS MySQL/PostgreSQL, Aurora, ElastiCache, OpenSearch, MSK)
- Lambda function with no native binary layer
- User did not explicitly opt out

### Ask in Clarify (tier=conditional with risk signals) when:

- Java with JNI dependencies (grep hits for `System.loadLibrary`)
- Python with C extensions beyond the standard set (niche packages)
- Rust/C/C++ without x86 assembly (recompile needed but likely fine)
- Ruby with native gem extensions not confirmed for arm64
- Proprietary/vendor AMIs without confirmed arm64 support

### Do NOT recommend Graviton (tier=incompatible) when:

- Windows workloads / .NET Framework
- GPU / CUDA workloads (route to G5/G6 instead)
- RDS SQL Server
- Known x86-only native dependencies without arm64 alternatives
- Heavy SSE/AVX SIMD usage without ARM NEON port
- Customer explicitly opted out in Clarify

---

## 9. Schema Extensions

### preferences.json — add architecture constraint

```json
"design_constraints": {
  "cpu_architecture": {
    "value": "graviton",
    "chosen_by": "default"
  }
}
```

Values: `"graviton"` | `"x86"` | `"mixed"`
`chosen_by`: `"user"` (explicit Clarify answer) | `"default"` (auto-applied for ready tier)

### aws-design.json — per-service override

```json
"graviton": {
  "compatibility": "ready",
  "target_architecture": "arm64",
  "caveats": []
}
```

### graviton_profile (emitted by Discover)

```json
{
  "service_name": "api-service",
  "tier": "ready",
  "signals": ["python-3.11", "no-native-extensions", "docker-multi-arch-base"],
  "caveats": [],
  "source": "app_code"
}
```

---

## 10. Skill File Layout

```
references/shared/graviton.md           ← This document (condensed)
references/shared/schema-graviton.md    ← graviton_profile schema
```

**SKILL.md conditional table entry:**

| File                 | Condition                                                           |
| -------------------- | ------------------------------------------------------------------- |
| `shared/graviton.md` | Any compute/database/cache in inventory OR graviton_profile present |

**Phase file touchpoints (minimal additions, not full pastes):**

| Phase file                  | Addition                                                    |
| --------------------------- | ----------------------------------------------------------- |
| discover-app-code.md        | Emit graviton_profile signals                               |
| discover-iac.md             | Dockerfile / machine_type signals                           |
| clarify-compute.md          | Q_graviton (conditional: any service tier != ready)         |
| design-refs/compute.md      | Branch on `preferences.design_constraints.cpu_architecture` |
| estimate-infra.md           | Dual-rate lookup + architecture_comparison block            |
| generate-artifacts-infra.md | runtimePlatform / architectures / instance_type             |
| pricing-cache.md            | ARM64 rates (§7 rows)                                       |

---

## 11. Tooling References

| Tool                              | Purpose                                                                 | Link                                                                                                                      |
| --------------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Porting Advisor for Graviton      | Scan source code for arm64 compatibility issues                         | [Blog](https://aws.amazon.com/blogs/compute/using-porting-advisor-for-graviton/)                                          |
| AWS Transform custom (ATX)        | AI-powered Java x86→Graviton migration agent                            | [Blog](https://aws.amazon.com/blogs/compute/migrating-your-java-applications-to-aws-graviton-using-aws-transform-custom/) |
| Graviton Savings Dashboard        | Visualize current usage + estimate savings (for existing AWS customers) | [Docs](https://docs.aws.amazon.com/guidance/latest/cloud-intelligence-dashboards/graviton-savings-dashboard.html)         |
| AWS Compute Optimizer             | Graviton migration effort ratings per instance                          | [Blog](https://aws.amazon.com/blogs/compute/aws-compute-optimizer-supports-aws-graviton-migration-guidance/)              |
| Graviton Getting Started (GitHub) | Language-specific guides, ISV compatibility list                        | [GitHub](https://github.com/aws/aws-graviton-getting-started)                                                             |
| Graviton universal skill          | Open-source Agent Skill for Graviton migration                          | [GitHub](https://github.com/aws/aws-graviton-getting-started/tree/main/tools/skills)                                      |

---

## 12. Example Output

### Design phase — service block

```markdown
### Compute: api-service (Cloud Run → ECS Fargate ARM64)

**Current:** GCP Cloud Run, 2 vCPU / 4 GB, auto-scaling 1–10 instances
**Recommended:** ECS Fargate on ARM64, 2 vCPU / 4 GB
**Graviton compatibility:** ✅ Ready (Python 3.11, no native C extensions detected)
**Architecture:** arm64-only (no multi-arch needed for full migration)

**Migration steps:**

1. Build container with `--platform linux/arm64`
2. Set ECS task definition `runtimePlatform.cpuArchitecture = ARM64`
3. No code changes required

**Post-migration:** Consider load testing and downsizing if CPU headroom appears.
```

### Estimate phase — architecture comparison block

```markdown
|                       | GCP (current) | AWS Graviton | AWS x86 (comparison) | Graviton savings |
| --------------------- | ------------- | ------------ | -------------------- | ---------------- |
| api-service (Fargate) | $180/mo       | $142/mo      | $178/mo              | 20% vs x86       |
| database (Aurora)     | $320/mo       | $256/mo      | $310/mo              | 17% vs x86       |
| cache (ElastiCache)   | $95/mo        | $76/mo       | $95/mo               | 20% vs x86       |
| **Total compute**     | **$595/mo**   | **$474/mo**  | **$583/mo**          | **18.7% vs x86** |

_Savings shown are hourly price differences only. Performance uplift from Graviton physical cores
may allow further downsizing after load testing — not included in this estimate._
```
