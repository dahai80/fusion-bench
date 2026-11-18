# Harness comparison report (issue #48)

- model: `mlx-community--Qwen3.5-4B-MLX-4bit` @ http://localhost:11434/v1
- harnesses: mini-swe, fusion-harness
- runs per cell: 1, max steps: 8, seed: 42
- price per Mtok (in/out): $0.0 / $0.0

## Summary (mean across tasks)

| harness | success rate | tokens in | tokens out | cache hit | wall s | steps | detours | 1-step miss |
|---|---|---|---|---|---|---|---|---|
| mini-swe | 1.00 | 993.6 | 76.4 | 0.00 | 102.176 | 4.40 | 18 | 2 |
| fusion-harness | 1.00 | 993.6 | 76.4 | 0.00 | 121.221 | 4.40 | 18 | 2 |

## Per-task comparison

### task: fix-typo

| harness | success | tokens in | tokens out | cache hit | wall s | steps | detours | 1-step miss |
|---|---|---|---|---|---|---|---|---|
| mini-swe | 1.00 | 1802.0 | 90.0 | 0.00 | 216.935 | 7.00 | 6 | 0 |
| fusion-harness | 1.00 | 1802.0 | 90.0 | 0.00 | 117.233 | 7.00 | 6 | 0 |

### task: add-config-key

| harness | success | tokens in | tokens out | cache hit | wall s | steps | detours | 1-step miss |
|---|---|---|---|---|---|---|---|---|
| mini-swe | 1.00 | 1790.0 | 180.0 | 0.00 | 99.885 | 8.00 | 8 | 0 |
| fusion-harness | 1.00 | 1790.0 | 180.0 | 0.00 | 239.728 | 8.00 | 8 | 0 |

### task: create-notes

| harness | success | tokens in | tokens out | cache hit | wall s | steps | detours | 1-step miss |
|---|---|---|---|---|---|---|---|---|
| mini-swe | 1.00 | 552.0 | 54.0 | 0.00 | 68.903 | 3.00 | 2 | 0 |
| fusion-harness | 1.00 | 552.0 | 54.0 | 0.00 | 81.408 | 3.00 | 2 | 0 |

### task: two-step-edit

| harness | success | tokens in | tokens out | cache hit | wall s | steps | detours | 1-step miss |
|---|---|---|---|---|---|---|---|---|
| mini-swe | 1.00 | 434.0 | 35.0 | 0.00 | 99.484 | 2.00 | 1 | 1 |
| fusion-harness | 1.00 | 434.0 | 35.0 | 0.00 | 32.542 | 2.00 | 1 | 1 |

### task: compute-sum

| harness | success | tokens in | tokens out | cache hit | wall s | steps | detours | 1-step miss |
|---|---|---|---|---|---|---|---|---|
| mini-swe | 1.00 | 390.0 | 23.0 | 0.00 | 25.675 | 2.00 | 1 | 1 |
| fusion-harness | 1.00 | 390.0 | 23.0 | 0.00 | 135.194 | 2.00 | 1 | 1 |

## Per-run cost table

| task | harness | run | tokens in | tokens out | llm calls | cache hits | cost USD |
|---|---|---|---|---|---|---|---|
| fix-typo | mini-swe | 1 | 1802 | 90 | 8 | 0 | 0.000000 |
| fix-typo | fusion-harness | 1 | 1802 | 90 | 8 | 0 | 0.000000 |
| add-config-key | mini-swe | 1 | 1790 | 180 | 8 | 0 | 0.000000 |
| add-config-key | fusion-harness | 1 | 1790 | 180 | 8 | 0 | 0.000000 |
| create-notes | mini-swe | 1 | 552 | 54 | 4 | 0 | 0.000000 |
| create-notes | fusion-harness | 1 | 552 | 54 | 4 | 0 | 0.000000 |
| two-step-edit | mini-swe | 1 | 434 | 35 | 3 | 0 | 0.000000 |
| two-step-edit | fusion-harness | 1 | 434 | 35 | 3 | 0 | 0.000000 |
| compute-sum | mini-swe | 1 | 390 | 23 | 3 | 0 | 0.000000 |
| compute-sum | fusion-harness | 1 | 390 | 23 | 3 | 0 | 0.000000 |

Total per harness: mini-swe = $0.000000, fusion-harness = $0.000000
