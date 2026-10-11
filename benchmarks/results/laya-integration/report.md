# Laya-MLX Integration Benchmark Report

**Timestamp**: 2026-10-11T09:46:42Z
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
| Tool Detection | accuracy | ≥ 80% | — | ⏭️ Skipped |
| E2E Latency | overhead (ms) | < 20 | — | ⏭️ Skipped |
| VRAM Isolation | laya resident | yes | False | ❌ |

## Baseline Comparison (laya vs random)

| Dimension | Laya | Random Baseline | Improvement |
|-----------|------|-----------------|-------------|

## Per-Dimension Guardrail Detail


## Test Sets

- Intent classification: 120 prompts (6 laya domain labels)
- Guardrail: 100 prompts (jailbreak/injection/sensitive/benign)
- Tool detection: 100 requests (7 tools + 16 no-tool)

## Notes

- Endpoint: fusion-mlx `/v1/laya/decide` (laya-multilingual-mlx, P0_NEVER_EVICT)
- Gateway LayaClassifier (fusion-gateway #191) calls this same endpoint internally
- Test sets committed to `benchmarks/testsets/` for reproducibility
- Intent labels aligned to laya's 6 domain choices (code/math_or_logic/writing/factual_lookup/data_analysis/chitchat)
- Guardrail: per-dimension thresholds (sensitive_data lowered to 0.25 — laya scores 0.27-0.43 for sensitive prompts)
- Tool detection: tests needs_tools.noul accuracy (laya has no native tool field)