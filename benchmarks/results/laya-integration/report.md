# Laya-MLX Integration Benchmark Report

**Timestamp**: 2026-10-11T12:21:54Z
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
| Tool Selection | structural success | ≥ 99.9% | — | ⏭️ Skipped |
| E2E Latency | overhead (ms) | < 20 | — | ⏭️ Skipped |
| VRAM Isolation | laya resident (baseline) | yes | False | ❌ |
| VRAM Isolation | resident under 32B load | yes | False | ❌ |
| Cold Start | first call (ms) | informational | 0 | ℹ️ |

## Baseline Comparison (laya vs random)

| Dimension | Laya | Random Baseline | Improvement |
|-----------|------|-----------------|-------------|

## Per-Dimension Guardrail Detail


## Test Sets

- Intent classification: 120 prompts (6 laya domain labels)
- Guardrail: 100 prompts (jailbreak/injection/sensitive/benign)
- Tool selection: 100 requests (7 tools + 16 no-tool)

## Notes

- Endpoint: fusion-mlx `/v1/laya/decide` (laya-multilingual-mlx, P0_NEVER_EVICT)
- Gateway LayaClassifier (fusion-gateway #191) calls this same endpoint internally
- Test sets committed to `benchmarks/testsets/` for reproducibility
- Intent labels aligned to laya's 6 domain choices (code/math_or_logic/writing/factual_lookup/data_analysis/chitchat)
- Guardrail: unified detection (any flag ≥ threshold → unsafe); sensitive_data threshold 0.10
- Tool selection: structural success (no malformed output, spec 99.9%) + selection accuracy (domain→tool mapping)
- VRAM: loads competing 27B model to verify P0_NEVER_EVICT holds under memory pressure
- Warmup: 5 warmup calls before latency measurement (cold start ~1-2s, hot P50 <15ms)