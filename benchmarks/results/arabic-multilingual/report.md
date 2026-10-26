# Arabic/Multilingual Evaluation Report (issue #32, ai-speech-exam G9)

**Timestamp**: 2026-10-26T09:48:20Z
**Model**: mlx-community--Qwen3.5-9B-4bit
**Mode**: direct-mlx
**Endpoint**: http://localhost:11434/v1/chat/completions
**Composite Score**: 1.0000

## Dimension Results (targets provisional — first baseline)

| Dimension | Metric | Provisional Target | Actual | Status |
|-----------|--------|--------------------|--------|--------|
| Translation AR→EN | chrF | ≥ 40.0 | 87.8 | ✅ | (BLEU 79.02, n=15) |
| Translation EN→AR | chrF | ≥ 35.0 | 73.45 | ✅ | (BLEU 46.65, n=15) |
| RTL Integrity | integrity | ≥ 90% | 100.0% | ✅ |
| Arabic Understanding | accuracy | ≥ 60% | 100.0% | ✅ |
| Arabic STT (roundtrip) | WER | ≤ 0.3 | — | ⏭️ Skipped (fusion-speech unavailable) |

## Notes

- Scoring: sacrebleu corpus BLEU + chrF (no torch/transformers — repo constraint).
- COMET-style neural metrics need model downloads; out of scope for this executor.
- RTL integrity checks: Arabic script present, no mojibake (UTF-8-as-Latin1),
  no legacy presentation forms (visual-order encoding), no U+FFFD.
- STT dim: fusion-speech TTS→STT roundtrip; auto-skips when the daemon is down
  (fusion-speech not running at benchmark time).
- Test sets committed to `benchmarks/testsets/` (hand-authored MSA).