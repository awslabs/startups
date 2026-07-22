---
_fragment: peripherals
_of_phase: generate
_contributes:
  - { file: "terraform/database.tf", _when: "Postgres peripheral detected" }
  - { file: "terraform/cache.tf", _when: "KV peripheral detected" }
  - { file: "terraform/storage.tf", _when: "Blob peripheral detected" }
  - { file: "terraform/scheduling.tf", _when: "Cron peripheral detected" }
---

# Generate Phase: Peripheral Resources

> Self-contained fragment. Always runs. Maps detected Vercel peripherals to
> production-ready AWS Terraform resources using `knowledge/peripheral-mappings.json`.
> Emits domain-specific `.tf` files only for peripherals actually detected.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 1: Load Peripheral Mappings

Read `knowledge/peripheral-mappings.json` for the Vercel -> AWS target table.
Read `discovery.json.peripherals[]` and `discovery.json.storage_integrations[]`
to determine which peripherals were detected.

---

## Step 2: Emit `terraform/database.tf` (If Postgres Detected)

```hcl
# RDS PostgreSQL — migrated from Vercel Postgres

resource "aws_db_subnet_group" "postgres" {
  name       = "${var.project_name}-${var.environment}-db"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "${var.project_name}-${var.environment}-db-subnet-group"
  }
}

resource "aws_db_instance" "postgres" {
  identifier     = "${var.project_name}-${var.environment}-postgres"
  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class
  allocated_storage = var.db_storage_gb

  db_name  = var.project_name
  username = "postgres"
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = [aws_security_group.database.id]
  multi_az               = var.db_multi_az
  storage_encrypted      = true
  skip_final_snapshot    = false
  final_snapshot_identifier = "${var.project_name}-${var.environment}-final"

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  tags = {
    Name = "${var.project_name}-${var.environment}-postgres"
  }
}
```

**Instance sizing** from `clarify-answers.json.Q7_database_size`:

| Answer    | Instance Class  | Storage |
| --------- | --------------- | ------- |
| < 1 GB    | `db.t4g.micro`  | 20 GB   |
| 1-10 GB   | `db.t4g.small`  | 50 GB   |
| 10-100 GB | `db.r6g.large`  | 200 GB  |
| > 100 GB  | `db.r6g.xlarge` | 500 GB  |
| unknown   | `db.t4g.small`  | 50 GB   |

Add a "Neon often correct to keep" advisory note as a comment:

```hcl
# NOTE: If your Vercel Postgres is backed by Neon, keeping it on Neon may be
# the better choice — Neon's serverless scaling and branching features don't
# have a direct RDS equivalent. Evaluate before migrating data.
```

---

## Step 3: Emit `terraform/cache.tf` (If KV Detected)

```hcl
# ElastiCache Redis — migrated from Vercel KV

resource "aws_elasticache_subnet_group" "redis" {
  name       = "${var.project_name}-${var.environment}-redis"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${var.project_name}-${var.environment}"
  description          = "Redis cache migrated from Vercel KV"
  node_type            = var.cache_node_type
  num_cache_clusters   = 1
  engine_version       = "7.1"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.redis.name
  security_group_ids   = [aws_security_group.cache.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  tags = {
    Name = "${var.project_name}-${var.environment}-redis"
  }
}
```

Add an "Upstash often correct to keep" advisory:

```hcl
# NOTE: If your Vercel KV is backed by Upstash, keeping it on Upstash may be
# simpler — Upstash provides serverless Redis with per-request billing that
# doesn't require VPC management. Evaluate before migrating.
```

---

## Step 4: Emit `terraform/storage.tf` (If Blob Detected)

```hcl
# S3 — migrated from Vercel Blob

resource "aws_s3_bucket" "storage" {
  bucket = "${var.project_name}-${var.environment}-storage"

  tags = {
    Name = "${var.project_name}-${var.environment}-storage"
  }
}

resource "aws_s3_bucket_versioning" "storage" {
  bucket = aws_s3_bucket.storage.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_public_access_block" "storage" {
  bucket                  = aws_s3_bucket.storage.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "storage" {
  bucket = aws_s3_bucket.storage.id

  rule {
    id     = "intelligent-tiering"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "INTELLIGENT_TIERING"
    }
  }
}
```

---

## Step 5: Emit `terraform/scheduling.tf` (If Cron Detected)

```hcl
# EventBridge Scheduler + Lambda — migrated from Vercel Cron

resource "aws_lambda_function" "cron" {
  function_name = "${var.project_name}-${var.environment}-cron"
  role          = aws_iam_role.lambda_execution.arn
  handler       = "index.handler"
  runtime       = "nodejs20.x"
  architectures = ["arm64"]
  memory_size   = 128
  timeout       = 60

  # Placeholder — replace with actual cron handler
  filename         = "cron-placeholder.zip"
  source_code_hash = ""

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-cron"
  }
}

resource "aws_scheduler_schedule" "cron" {
  name       = "${var.project_name}-${var.environment}-cron"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "rate(1 hour)"  # TODO: match your Vercel cron schedule

  target {
    arn      = aws_lambda_function.cron.arn
    role_arn = aws_iam_role.scheduler.arn
  }
}
```

**Graviton (ARM64):** Lambda cron invoker defaults to ARM64 per
`references/shared/graviton.md`.

---

## Step 6: Wire M2 Remediation (If Applicable)

If `preflight-findings.json`'s M2 check (geo/IP header dependence) was
detected, emit a CloudFront Function for header mapping. Note in
`terraform/README.md` that enabling viewer-geolocation forwarding at the
distribution level is a required manual step.

---

## Step 7: Outcome C Separability Cross-Check

When `recommendation.json.outcome == "C"`: for each peripheral emitted, check
whether its associated route (if any) is in `discovery.json.api_routes[]`. If
NOT, still emit the resource but flag it in `terraform/README.md`:

> "This peripheral's associated route was not part of the surface Recommend
> determined separable — verify its logic doesn't depend on app code remaining
> on Vercel before relying on this resource."

---

## Output Contribution for Parent Orchestrator

Conditional `.tf` files — only for peripherals actually detected. If no
peripherals were detected, this fragment contributes nothing (and that's fine).

---

## Scope Boundary

**This fragment covers peripheral resource Terraform ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Compute resources (ECS, Lambda for the app — those are compute fragments)
- `baseline.tf` resources
- VPC or core Terraform (those are `generate-terraform.md`'s job)

**Your ONLY job: map peripherals to Terraform. Nothing else.**
