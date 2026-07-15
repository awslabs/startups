# Generated-IaC Security Posture Rules

Cross-cutting security posture that generated AWS Terraform must follow, regardless of the
source cloud. These are **authoring rules** ("what to emit"); the read-only policy gate
(`scripts/validate-terraform-policy.py`) verifies the subset it can check statically.

> **Scope.** tf-best-practices owns these posture areas as authoring rules AND enforces them
> in the read-only gate: internet-facing ALB TLS, no-public-database, no-public-DB-port
> ingress, no-wildcard-IAM, and RDS encryption-at-rest. Each gate rule is **fail-open on
> ambiguity** — it fires only on unambiguous, in-block literal evidence, so a valid stack is
> never falsely blocked (the mirror of the ALB rule's fail-safe stance). Remaining posture
> areas (private-subnet placement as a positive assertion, the account-hardening `baseline.tf`
> layer, S3 SSE correlation) stay the consuming skill's own generation rules for now and are
> candidates to migrate here later.

## Internet-facing ALB — TLS termination and HTTP redirect

**Applies when:** an `aws_lb` is an internet-facing **Application** load balancer —
`internal = false`, omitted, or variable-driven (treated as internet-facing, fail-safe).
Exempt: internal ALBs (`internal = true`), and **Network (L4) / Gateway (L3) load balancers**
(`load_balancer_type = "network"` or `"gateway"`) — these front raw TCP/UDP and legitimately
have no HTTPS:443 listener.

**Rules:**

1. Emit an HTTPS listener on port `443` (`protocol = "HTTPS"`) with a modern `ssl_policy`, a
   `certificate_arn`, and a `forward` default action to the app target group.
2. Emit an HTTP listener on port `80` whose default action is a **redirect** to HTTPS
   (`HTTP_301`) — never a `forward` to targets.
3. The ALB security group allows `443` from the internet and `80` only for the redirect;
   never forward plaintext HTTP to targets. Target groups may use HTTP to the tasks behind
   the ALB — TLS terminates at the ALB.

**Reference HCL (emit whenever `aws_lb` is internet-facing):**

```hcl
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.app.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.app.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for the public ALB HTTPS listener"
  type        = string
  # TODO: request or import a certificate for your app domain
}
```

**Gate mapping:** rule 1 → `alb_https_listener`; rule 2 → `alb_http_redirect`
(see `scripts/validate-terraform-policy.py`). If generated Terraform lacks the HTTPS
listener or forwards HTTP, that is a generation defect the caller must fix — not a reason to
draw or ship plaintext HTTP.

## Managed database — no public exposure

**Applies to:** `aws_db_instance`, `aws_rds_cluster`.

**Rules:**

1. Never emit `publicly_accessible = true`. Place the database in private subnets and reach it
   from application security groups only. RDS defaults to `false`, so simply omitting the
   attribute is compliant.
2. Emit `storage_encrypted = true` — RDS storage defaults to **unencrypted**, so this must be
   explicit. Optionally set `kms_key_id` for a customer-managed key.

**Gate mapping:** rule 1 → `rds_not_public`; rule 2 → `rds_encryption_at_rest`. The gate fires
only on a literal `publicly_accessible = true` / missing-or-`false` `storage_encrypted`; a
variable-driven value fails open (not flagged). S3 is not checked — buckets have default SSE-S3
since Jan 2023, so a missing SSE block is not an unencrypted bucket.

## ElastiCache — encryption at rest

**Applies to:** `aws_elasticache_replication_group`.

**Rule:** set `at_rest_encryption_enabled = true` (and consider
`transit_encryption_enabled = true`). ElastiCache does not encrypt at rest by default.

**Gate mapping:** `elasticache_encryption_at_rest`. Fires on missing-or-`false`; variable-driven
fails open. `aws_elasticache_cluster` (standalone Memcached) is not checked — that attribute is
configured on the replication group.

## Database security group — no public ingress on DB ports

**Applies to:** inline `ingress { ... }` blocks inside `aws_security_group`.

**Rule:** an ingress rule covering a database port (`5432` PostgreSQL, `3306` MySQL) must not
allow `0.0.0.0/0`. Restrict to the application security group (`security_groups = [...]`) or a
private CIDR.

**Gate mapping:** `db_sg_no_public_ingress`. The gate inspects only inline ingress blocks;
separate `aws_security_group_rule` / `aws_vpc_security_group_ingress_rule` resources fail open
(the static reader cannot correlate them to their security group), so prefer inline ingress
where you want gate coverage.

## Security group — no public admin / datastore ports

**Applies to:** inline `ingress { ... }` blocks inside `aws_security_group`.

**Rule:** an ingress rule must not open a well-known admin or datastore port to `0.0.0.0/0`.
The enforced set is deliberately fixed to ports that are ~never legitimately public: `22`
(SSH), `3389` (RDP), `6379` (Redis), `11211` (Memcached), `27017` (MongoDB), `9200`/`9300`
(Elasticsearch), `5601` (Kibana). Reach these from a bastion/app security group or a private
CIDR instead.

**Gate mapping:** `sg_no_public_admin_ingress`. Web ports (`80`/`443`) and application/game
ports (e.g. high ranges) are **not** flagged — the rule targets a curated never-public list,
not "any public ingress", so legitimately-public workloads pass. Database ports (`5432`/`3306`)
are handled by `db_sg_no_public_ingress` and excluded here to avoid double-reporting. Same
inline-only fail-open scope as that rule.

## IAM — no wildcard permissions

**Applies to:** `aws_iam_policy`, `aws_iam_role_policy`, `aws_iam_group_policy`,
`aws_iam_user_policy`.

**Rule:** an `Allow` statement must not use a sole wildcard for `Action` or `Resource`, in
either string form (`"*"`) or single-element list form (`["*"]`). Scope to specific actions
and resource ARNs. A list that also contains scoped entries (e.g. `["s3:GetObject", ...]`) is
not a blanket wildcard and is allowed.

**Gate mapping:** `no_wildcard_iam`. The gate scans literal policy JSON (heredoc or
`jsonencode({...})`) in the resources above. `aws_iam_policy_document` **data sources** fail
open (their statements are HCL blocks, not literal JSON the reader can inspect), and assume-role
trust policies on `aws_iam_role` are out of scope — so a scoped data-source policy is never
falsely flagged.
