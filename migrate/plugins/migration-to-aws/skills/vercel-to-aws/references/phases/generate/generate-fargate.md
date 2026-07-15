---
_fragment: compute-fargate
_of_phase: generate
_contributes:
  - terraform/compute.tf
  - terraform/cdn.tf
---

# Generate Phase: Outcome B (ECS Fargate) or Outcome C's B-Shaped Backend

> Self-contained compute fragment. Fires when `recommendation.json.outcome ==
> "B"` (full app-surface) OR `outcome == "C"` with `backend_shape ==
> "B-shaped"` (backend-only). Terraform only — this fragment NEVER emits SST
> or OpenNext artifacts.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 0: Determine Mode

Read `recommendation.json.outcome`:

- **`outcome == "B"`:** Full app-surface mode — the entire Next.js app
  (via `next start` container) migrates to Fargate.
- **`outcome == "C"` and `backend_shape == "B-shaped"`:** Backend-only mode —
  only the separable backend runs on Fargate; the Next.js app stays on Vercel.

Both modes are Terraform-only. The distinction affects WHAT gets containerized.

---

## Step 1: Emit `terraform/compute.tf`

### Full App-Surface Mode (Outcome B)

```hcl
# ECS Fargate — Full Next.js application via `next start`
#
# Outcome B: the entire app migrates to a containerized Fargate service.

resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "app" {
  family                   = "${var.project_name}-${var.environment}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.container_cpu
  memory                   = var.container_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([{
    name  = "app"
    image = var.container_image
    portMappings = [{
      containerPort = 3000
      protocol      = "tcp"
    }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.app.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "app"
      }
    }
    environment = []
    secrets     = []
  }])
}

resource "aws_ecs_service" "app" {
  name            = "${var.project_name}-${var.environment}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "app"
    container_port   = 3000
  }
}

resource "aws_appautoscaling_target" "ecs" {
  max_capacity       = 10
  min_capacity       = var.desired_count
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.app.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "cpu" {
  name               = "${var.project_name}-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value = 70.0
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

resource "aws_lb" "app" {
  name               = "${var.project_name}-${var.environment}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
}

resource "aws_lb_target_group" "app" {
  name        = "${var.project_name}-${var.environment}-tg"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/api/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
  }
}

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

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.project_name}-${var.environment}"
  retention_in_days = 30
}

resource "aws_ecr_repository" "app" {
  name                 = "${var.project_name}-${var.environment}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}
```

**Graviton (ARM64):** The `runtime_platform` block defaults to ARM64 per
`references/shared/graviton.md`. Note in `terraform/README.md` that
`docker buildx build --platform linux/arm64` is required.

### Backend-Only Mode (Outcome C, B-shaped)

Same Fargate stack structure but scoped to the separable backend surface only.
Add inline documentation:

```hcl
# This backend-only Fargate service serves Outcome C (Hybrid).
# Your Next.js app and its PR previews remain on Vercel.
# Only the separable backend surface migrates to AWS.
```

Adjust the health check path and container configuration to match the backend
service, not the full Next.js app.

---

## Step 2: Emit `terraform/cdn.tf`

```hcl
# CloudFront distribution fronting the ALB

resource "aws_cloudfront_distribution" "main" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = ""
  price_class         = "PriceClass_100"

  origin {
    domain_name = aws_lb.app.dns_name
    origin_id   = "alb"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "alb"
    viewer_protocol_policy = "redirect-to-https"

    forwarded_values {
      query_string = true
      headers      = ["Host", "Origin", "Authorization"]
      cookies {
        forward = "all"
      }
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-cdn"
  }
}
```

---

## Step 3: Wire Pre-Flight Remediations

- **I1 (ISR multi-instance):** If ISR is present and `desired_count > 1`,
  provision a shared cache (ElastiCache or cache-control headers + CloudFront
  invalidation). If `desired_count == 1`, add a warning comment on the
  autoscaling target: "raising task count above 1 requires a shared cache for
  ISR — see Pre-Flight Check I1."
- **M1 (edge middleware):** Wire CloudFront Functions for simple
  header/redirect logic that would otherwise require edge middleware.

---

## Output Contribution for Parent Orchestrator

`terraform/compute.tf` + `terraform/cdn.tf`.

---

## Scope Boundary

**This fragment covers Fargate compute and CloudFront for Outcome B / C-B ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Emitting `sst.config.ts` or any OpenNext artifact
- Peripheral resources (RDS, ElastiCache, S3 — those are other fragments' jobs)
- Firing alongside `compute-opennext` or `compute-lambda`

**Your ONLY job: emit Fargate + CloudFront Terraform. Nothing else.**
