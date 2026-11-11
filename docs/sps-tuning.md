---
doc_id: fusion-bench/sps-tuning
product: fusion-bench
class: platform
entry: service
doc_type: guide
title: { zh: "SPS 投机解码预算调优", en: "SPS Speculative-Decoding Budget Tuning" }
audience: engineer
status: draft
version: 0.4.27
updated: 2026-11-11
owner: "@dahai"
source_of_truth:
  - fusion_bench/sps/tuner.py
  - fusion_bench/sps/profile.py
  - README.md
---

# SPS Speculative-Decoding Budget Tuning (issue #43)

Benchmark-driven draft-token budget tuning for fusion-mlx speculative decoding, generalized from Tencent DSpine's `scripts/tune_sps.py` pattern (Apache-2.0, arXiv 2609.36173).

## Sweep mechanics

- **Input**: JSONL prefix file, one per line — `{"prompt": "...", "sampling_params": {"temperature": 0.0}}`. Use >= 8 distinct prefixes covering context lengths, tasks and reasoning levels; tune greedy and temperature sampling as separate runs. `input_ids`-only rows are skipped (the bench never loads a tokenizer).
- **Candidates**: draft widths x batch sizes. Batch size is real client-side concurrency (async). Width rides the request body as `speculative: {"draft_tokens": W}` — applied once fusion-mlx accepts per-request speculative params ([fusion-mlx#1528](https://github.com/dahai80/fusion-mlx/issues/1528)); until then the sweep degrades to the batch axis and the profile says so (`engine_spec_support: "unverified"`).
- **Scoring**: one untimed warm pass, then N timed repeats per candidate; each repeat = one concurrent batch, scored by total completion tokens / wall time (prefill + request overhead included). Median wins.
- **Secondary metric**: acceptance length from engine metrics when exposed (null today, same upstream issue).

## Commands

```bash
# full sweep
fusion-bench sps tune --prefixes prefixes.jsonl \
  --widths 4,8,12,16 --batch-sizes 1,2,4 --repeats 3 \
  --max-tokens 128 --output sps.json

# staleness check (retune trigger: hardware / model / workload change)
fusion-bench sps check --profile sps.json --prefixes prefixes.jsonl
```

## Profile artifact

`sps.json` (schema `fusion-bench.sps/v1`) records the sweep table, per-batch best widths, and provenance: chip, RAM tier, model, engine base URL, prefix-file sha256 digest, `generated_at`. A sample live profile is committed at `docs/baselines/sps-live-sample.json`. Retune whenever `sps check` reports stale.
