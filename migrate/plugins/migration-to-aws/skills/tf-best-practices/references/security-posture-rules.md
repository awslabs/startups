# Generated-IaC Security Posture Rules

Cross-cutting security posture that generated AWS Terraform must follow, regardless of the
source cloud. These are **authoring rules** ("what to emit"); the read-only policy gate
(`scripts/validate-terraform-policy.py`) verifies the subset it can check statically.

> **v1 scope.** Only the **internet-facing ALB TLS** posture below is currently owned by
> tf-best-practices (authoring rule + enforced by the gate). Other posture areas
> (private-subnet placement, no public database, encryption-at-rest, account-hardening
> `baseline.tf`) remain the consuming skill's own generation rules for now and are candidates
> to migrate here later. This file is the home they would move into.

## Internet-facing ALB — TLS termination and HTTP redirect

**Applies when:** an `aws_lb` is internet-facing — `internal = false`, or `internal` is
omitted, or `internal` is variable-driven (treated as internet-facing, fail-safe). Internal
ALBs (`internal = true`) are exempt.

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
