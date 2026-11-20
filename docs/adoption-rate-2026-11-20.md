---
doc_id: fusion-bench/architecture
product: fusion-bench
class: platform
entry: service
audience: engineer
status: draft
version: 0.4.36
updated: 2026-11-20
owner: "@dahai"
doc_type: architecture
title: { zh: "fusion-harness 采用率快照", en: "fusion-harness adoption-rate snapshot" }
source_of_truth:
  - docs/adoption-rate-2026-11-19.json
---

# fusion-harness adoption-rate snapshot (2026-11-20)

- Exports: 91  |  Consumer-direct (A): 74  |  Kernel-integrated (I): 11  |  **Delivered rate: 93.4%** (consumer-direct 81.3%; target 80%, met)
- Zero-consumer names (6): AWAITING_HUMAN_MARKER, FANOUT_COMPLEX_MAX, FANOUT_HARD_MAX, FANOUT_SIMPLE_MAX, MULTI_AGENT_TOKEN_MULTIPLIER, TOKEN_MULTIPLIER_WARNING

| name | consumers | tier |
|---|---|---|
| AWAITING_HUMAN_MARKER | - | B |
| ApprovalGate | fusion-agent-studio, fusion-cowork | A |
| ArtifactQuarantine | fusion-agent-studio, fusion-cowork | A |
| ArtifactStore | fusion-agent-studio | A |
| ArtifactTools | fusion-agent-studio | A |
| BackgroundPool | fusion-agent-studio | A |
| BaseNode | fusion-cowork | A |
| CJKAwareHeuristicTokenCounter | fusion-agent-studio | A |
| CacheTelemetry | fusion-agent-studio | A |
| CheckpointState | fusion-agent-studio, fusion-cowork | A |
| CheckpointStore | fusion-agent-studio, fusion-cowork | A |
| CompactionConfig | fusion-agent-studio, fusion-cowork, console | A |
| Compactor | fusion-agent-studio, fusion-cowork, console | A |
| ConfirmationPolicy | fusion-agent-studio | A |
| ExecutionTier | fusion-agent-studio, fusion-cowork | A |
| FANOUT_COMPLEX_MAX | - | B |
| FANOUT_HARD_MAX | - | B |
| FANOUT_SIMPLE_MAX | - | B |
| FailureAnalyzer | fusion-cowork | A |
| HeuristicTokenCounter | - | I |
| HookConfig | fusion-agent-studio, fusion-cowork | A |
| HookEngine | fusion-agent-studio, fusion-cowork | A |
| HookResult | fusion-agent-studio, fusion-cowork | A |
| HumanGate | fusion-agent-studio, fusion-cowork | A |
| JSONRepairError | fusion-agent-studio, fusion-cowork | A |
| KERNEL_VERSION | - | I |
| LLMFunnel | fusion-agent-studio, fusion-cowork, console | A |
| LifecycleBus | fusion-agent-studio, fusion-cowork, console | A |
| LoopDetector | - | I |
| MSG_TYPES | fusion-cowork | A |
| MULTI_AGENT_TOKEN_MULTIPLIER | - | B |
| NodeRegistry | fusion-cowork | A |
| NodeRegistryError | fusion-cowork | A |
| OutboxStore | fusion-agent-studio, fusion-cowork | A |
| ParallelTeam | fusion-agent-studio, fusion-cowork | A |
| PermissionDecision | fusion-agent-studio, fusion-cowork | A |
| PermissionEngine | fusion-agent-studio, fusion-cowork, console | A |
| PermissionMode | fusion-agent-studio, fusion-cowork | A |
| PermissionRule | fusion-agent-studio, fusion-cowork, console | A |
| Playbook | fusion-agent-studio | A |
| PlaybookOp | fusion-agent-studio | A |
| ReceiptCache | fusion-cowork | A |
| RetryPolicy | fusion-agent-studio | A |
| SandboxExecRunner | fusion-cowork | A |
| SandboxPolicy | fusion-agent-studio, fusion-cowork | A |
| SandboxRunner | fusion-cowork | A |
| ScanReport | - | I |
| ScopedPermission | fusion-cowork | A |
| ScopedPermissionEngine | fusion-cowork | A |
| ScopedPermissionError | fusion-cowork | A |
| SessionEventLog | fusion-agent-studio | A |
| Skill | fusion-agent-studio | A |
| SkillError | fusion-agent-studio | A |
| SkillRegistry | fusion-agent-studio | A |
| SpawnBrief | fusion-agent-studio | A |
| SpawnBriefError | fusion-agent-studio | A |
| SubagentRunner | fusion-agent-studio, fusion-cowork | A |
| SubagentSpec | fusion-agent-studio, fusion-cowork | A |
| SummaryInjector | fusion-agent-studio | A |
| TOKEN_MULTIPLIER_WARNING | - | B |
| TeamDefError | fusion-cowork | A |
| TeamDefinition | fusion-agent-studio, fusion-cowork | A |
| TeamMember | fusion-agent-studio, fusion-cowork | A |
| TeamMessage | fusion-agent-studio, fusion-cowork | A |
| TeamMessageError | fusion-cowork | A |
| TeamRuntime | fusion-agent-studio, fusion-cowork | A |
| TeamTask | fusion-agent-studio | A |
| TokenCounter | - | I |
| ToolFunnel | fusion-agent-studio, fusion-cowork, console | A |
| ToolPipeline | fusion-agent-studio | A |
| TopologyError | - | I |
| TopologySelector | - | I |
| TrajectoryRecord | fusion-agent-studio, fusion-cowork | A |
| TrajectorySchemaError | fusion-agent-studio | A |
| TrajectoryWriter | fusion-agent-studio | A |
| WorkerDelivery | fusion-agent-studio | A |
| bind_node_state | fusion-agent-studio | A |
| brief_from_event | fusion-agent-studio | A |
| cite_link | - | I |
| count_messages | - | I |
| extract_links | - | I |
| fanout_warnings | fusion-cowork | A |
| idempotency_key | - | I |
| mask_tools | fusion-agent-studio | A |
| normalize_record | fusion-agent-studio | A |
| parse_repair | fusion-agent-studio, fusion-cowork | A |
| parse_skill | fusion-agent-studio | A |
| scan_artifact | fusion-agent-studio, fusion-cowork | A |
| score_tool_risk | fusion-agent-studio | A |
| stamp_untrusted | fusion-agent-studio | A |
| validate_brief | fusion-agent-studio | A |
