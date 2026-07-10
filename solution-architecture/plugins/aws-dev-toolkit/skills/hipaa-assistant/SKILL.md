---
name: hipaa-assistant
description: >
  Activate when the user asks about HIPAA compliance scanning, validating AWS
  configurations against HIPAA Security Rule controls, or pre-deployment HIPAA
  checks for GenAI workloads on AWS.
---

# HIPAA Assistant

A Go-based CLI and MCP server that scans your AWS configurations against HIPAA
Security Rule controls before deployment.

## What it does

- **Scan** - Analyzes CloudFormation, Terraform, or application code for HIPAA
  Security Rule compliance gaps
- **Advise** - Provides remediation steps for identified gaps
- **Reference** - Maps each finding to the verbatim Code of Federal Regulations
  text (45 CFR Part 164) so you know exactly which control is at risk

## How to use it

https://github.com/aws-samples/sample-hipaa-assistant

Runs as a CLI tool or as an MCP server you can invoke directly from your IDE.

## Disclaimer

This tool provides cited technical guidance based on publicly available HIPAA
Security Rule text (45 CFR Part 164) and AWS documentation. It is not legal
advice and does not constitute a compliance certification. Work with qualified
legal counsel and compliance professionals before handling PHI in production.
