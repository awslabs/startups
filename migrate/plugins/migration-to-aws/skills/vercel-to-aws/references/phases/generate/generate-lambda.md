---
_fragment: compute-lambda
_of_phase: generate
_contributes:
  - terraform/compute.tf
---

# Generate Phase: Outcome C's A-Shaped Backend (API Gateway + Lambda)

> Self-contained compute fragment. Fires ONLY when `recommendation.json.outcome
> == "C"` AND `backend_shape == "A-shaped"`. Emits Terraform for a serverless
> backend (API Gateway + Lambda) covering the separable API routes. The Next.js
> app itself remains on Vercel — this fragment NEVER emits SST, OpenNext, or
> full-app hosting.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 1: Emit `terraform/compute.tf`

```hcl
# API Gateway + Lambda — Outcome C (Hybrid) Backend
#
# This backend-only scaffold serves Outcome C (Hybrid). Your Next.js app and
# its PR previews remain on Vercel. Only the separable backend surface below
# migrates to AWS as API Gateway + Lambda.

resource "aws_apigatewayv2_api" "backend" {
  name          = "${var.project_name}-${var.environment}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 86400
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-api"
  }
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.backend.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      path           = "$context.path"
      status         = "$context.status"
      responseLength = "$context.responseLength"
    })
  }
}

resource "aws_lambda_function" "backend" {
  function_name = "${var.project_name}-${var.environment}-backend"
  role          = aws_iam_role.lambda_execution.arn
  handler       = "index.handler"
  runtime       = "nodejs20.x"
  architectures = ["arm64"]
  memory_size   = var.lambda_memory_size
  timeout       = var.lambda_timeout

  # Placeholder — replace with actual deployment package
  filename         = "placeholder.zip"
  source_code_hash = ""

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      NODE_ENV = "production"
    }
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-backend"
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.backend.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.backend.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.backend.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.backend.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.backend.execution_arn}/*/*"
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigateway/${var.project_name}-${var.environment}"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-backend"
  retention_in_days = 30
}
```

**Graviton (ARM64):** The `architectures = ["arm64"]` is set by default per
`references/shared/graviton.md`.

---

## Step 2: Wire M1 Remediation (If Applicable)

If `preflight-findings.json`'s M1 check was HIGH severity AND the backend's
own routes intersect with CDN-cacheable paths, add a note in
`terraform/README.md` about header/redirect logic that may need a CloudFront
Function (the peripherals fragment owns the actual CloudFront resource if
the backend needs one — this fragment just documents the dependency).

---

## Output Contribution for Parent Orchestrator

`terraform/compute.tf` only. This fragment does NOT emit `terraform/cdn.tf`
(unlike the Fargate fragment) — API Gateway provides its own HTTPS endpoint;
CloudFront is optional for backend-only APIs and handled by the peripherals
fragment if needed.

---

## Error Handling

| Error Category                       | Behavior                                                                                                                                    |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| No separable backend routes detected | Surface a diagnostic — this should not happen if `recommendation.outcome == "C"` (the engine only recommends C when separable routes exist) |

---

## Scope Boundary

**This fragment covers Outcome C's A-shaped serverless backend ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Emitting `sst.config.ts` or any OpenNext/SST artifact
- Full-app Fargate hosting
- Peripheral resources (RDS, ElastiCache, S3)
- Firing alongside `compute-opennext` or `compute-fargate`

**Your ONLY job: emit API Gateway + Lambda Terraform for the separable
backend. Nothing else.**
