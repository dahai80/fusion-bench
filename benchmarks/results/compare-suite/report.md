# Shared-task comparison suite report (PARTIAL)

> completion/tokens partial: fusion-mlx 0.10.67 blocks sustained agent traffic (dahai80/fusion-mlx#1665). HITL / compaction / dag / simplicity complete. (2026-11-20)

- Model: `mlx-community--Qwen3.5-4B-MLX-4bit` @ http://127.0.0.1:11434/v1 (X-Cache: bypass)
- langgraph pinned: 1.2.10 | smoke: False | issue: #53

- **fusion-harness**: completion rate 67%, wall 278.4s
- **langgraph**: completion rate n/a (blocked), wall -
- completion/tokens status: partial - upstream fusion-mlx#1665 (burst-scheduler IndexError under sustained agent traffic) blocks a clean sustained run; own-arm numbers from a degraded run with retries (wall inflated, provider token counts exact); rival arm blocked mid-run; smoke run (1 task) passed 1/1 on both arms earlier the same day before engine degradation

| side | tokens / completed task |
|---|---|
| fusion-harness | 1435.5 |
| langgraph | n/a (no completions) |

| side | kill-9 mid-wait -> resumed | resume wall (s) |
|---|---|---|
| fusion-harness | 1/1 | 0.4139 |
| langgraph | 1/1 | 0.4097 |

- **fusion-harness** compaction recall: pinned_goal=True latest_instruction=True facts_retained=8/8 score=1.0
- **langgraph** compaction recall: pinned_goal=False latest_instruction=True facts_retained=8/8 score=0.5

- DAG recovery (cowork): recovered=True after 2 injected failure(s)
- DAG recovery (dify): unavailable: dify is not installed locally and no network LLM/setup calls are allowed in the freeze window

| repo | runtime deps | LOC/node file | cold-start (s) | source |
|---|---|---|---|---|
| cowork | 11 | 178.9 | 0.226 | measured live |
| dify | None | None | None | offline-frozen: app distribution, not on PyPI; not installed locally |

