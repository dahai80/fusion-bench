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
- **Candidates**: draft widths x batch sizes. Batch size is real client-side concurrency (async). Width rides the request body as `speculative: {"draft_tokens": W}` — fusion-mlx >= 0.10.59 honors it on the **single-request pure-decode path** (widths valid 1-4); batched traffic falls back to the server default. The engine echoes the applied spec config on every response, and the tuner records `width_applied_rate` per candidate; the profile flips `engine_spec_support` to `"verified"` once any echo confirms application ([fusion-mlx#1528](https://github.com/dahai80/fusion-mlx/issues/1528)).
- **Scoring**: one untimed warm pass, then N timed repeats per candidate; each repeat = one concurrent batch, scored by total completion tokens / wall time (prefill + request overhead included). Median wins.
- **Secondary metric**: acceptance length from `/stats` `spec_decode.<strategy>.acceptance_length` (or `/v1/metrics` Prometheus lines) — counters are meaningful only when the engine runs with native MTP enabled (`verifies > 0`); otherwise the profile records `null`.

## Commands

```bash
# full sweep (widths: engine accepts 1-4; batched traffic falls back to
# the server default — width tuning is meaningful at batch size 1)
fusion-bench sps tune --prefixes prefixes.jsonl \
  --widths 1,2,4 --batch-sizes 1,2,4 --repeats 3 \
  --max-tokens 128 --output sps.json

# staleness check (retune trigger: hardware / model / workload change)
fusion-bench sps check --profile sps.json --prefixes prefixes.jsonl
```

## Profile artifact

`sps.json` (schema `fusion-bench.sps/v1`) records the sweep table, per-batch best widths, and provenance: chip, RAM tier, model, engine base URL, prefix-file sha256 digest, `generated_at`. A sample live profile is committed at `docs/baselines/sps-live-sample.json`. Retune whenever `sps check` reports stale.
