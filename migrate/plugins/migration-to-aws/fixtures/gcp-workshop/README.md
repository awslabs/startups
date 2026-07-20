# GCP what-if workshop fixtures

Infra-route pilot for `gcp-to-aws` (`references/phases/workshop/`).

| Path | Role |
| ---- | ---- |
| `seed/` | Post-Estimate baseline (`cpu_architecture=x86`) |
| `after-graviton-reprice/` | After Apply with `cpu_architecture=graviton` |
| `check_expected_workshop.py` | Stdlib asserter |

```bash
python3 check_expected_workshop.py after-graviton-reprice
```

Fresh-agent replay bar: copy `seed/` → enter workshop → set arch graviton → Apply → Compare → asserter PASS.
