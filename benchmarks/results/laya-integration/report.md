# Laya-MLX Integration Benchmark Report

**Timestamp**: 2026-10-10T23:43:16Z
**Model**: 
**Endpoint**: http://localhost:11434/v1/laya/decide
**Laya Available**: ❌ No (fusion-mlx laya endpoint not running)
**Composite Score**: 0.0000

## Spec Target Comparison

| Dimension | Metric | Spec Target | Actual | Status |
|-----------|--------|-------------|--------|--------|
| Decision Latency | P50 (ms) | < 15 | — | ⏭️ Skipped |
| Intent Accuracy | accuracy | > 80% | — | ⏭️ Skipped |
| Guardrail | precision | > 90% | — | ⏭️ Skipped |
| Tool Selection | accuracy | ≥ 99.9% | — | ⏭️ Skipped |
| E2E Latency | overhead (ms) | < 20 | — | ⏭️ Skipped |
| VRAM Isolation | laya resident | yes | False | ❌ |

## Test Sets

- Intent classification: 200 prompts
- Guardrail: 100 prompts
- Tool selection: 100 requests

## Notes

- Endpoint: fusion-mlx `/v1/laya/decide` (laya-multilingual-mlx, P0_NEVER_EVICT)
- Gateway LayaClassifier (fusion-gateway #191) calls this same endpoint internally
- Test sets committed to `benchmarks/testsets/` for reproducibility