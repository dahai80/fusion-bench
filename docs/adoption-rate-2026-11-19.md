---
doc_id: fusion-bench/architecture
product: fusion-bench
class: platform
entry: service
audience: engineer
status: draft
version: 0.4.36
updated: 2026-11-19
owner: "@dahai"
doc_type: architecture
title: { zh: "fusion-harness 采用率快照", en: "fusion-harness adoption-rate snapshot" }
source_of_truth:
  - docs/adoption-rate-2026-11-19.json
---

# fusion-harness adoption-rate snapshot (2026-11-19)

- Exports: 84  |  Consumer-direct (A): 72  |  Kernel-integrated (I): 12  |  **Delivered rate: 100.0%** (consumer-direct 85.7%; target 80%, met)
- Zero-consumer names (0): (none)

| name | consumers | tier |
|---|---|---|
| ApprovalGate | agent-studio, cowork | A |
| ArtifactQuarantine | agent-studio, cowork | A |
| ArtifactStore | agent-studio | A |
| ArtifactTools | agent-studio | A |
| BackgroundPool | agent-studio | A |
| BaseNode | cowork | A |
| CJKAwareHeuristicTokenCounter | agent-studio | A |
| CacheTelemetry | agent-studio | A |
| CheckpointState | agent-studio, cowork | A |
| CheckpointStore | agent-studio, cowork | A |
| CompactionConfig | agent-studio, cowork, console | A |
| Compactor | agent-studio, cowork, console | A |
| ConfirmationPolicy | agent-studio | A |
| ExecutionTier | agent-studio, cowork | A |
| FailureAnalyzer | - | I |
| HeuristicTokenCounter | - | I |
| HookConfig | agent-studio, cowork | A |
| HookEngine | agent-studio, cowork | A |
| HookResult | agent-studio, cowork | A |
| HumanGate | agent-studio, cowork | A |
| JSONRepairError | agent-studio, cowork | A |
| KERNEL_VERSION | - | I |
| LLMFunnel | agent-studio, cowork, console | A |
| LifecycleBus | agent-studio, cowork, console | A |
| LoopDetector | - | I |
| MSG_TYPES | cowork | A |
| NodeRegistry | cowork | A |
| NodeRegistryError | cowork | A |
| OutboxStore | agent-studio, cowork | A |
| ParallelTeam | agent-studio, cowork | A |
| PermissionDecision | agent-studio, cowork | A |
| PermissionEngine | agent-studio, cowork, console | A |
| PermissionMode | agent-studio, cowork | A |
| PermissionRule | agent-studio, cowork, console | A |
| Playbook | agent-studio | A |
| PlaybookOp | agent-studio | A |
| ReceiptCache | cowork | A |
| RetryPolicy | agent-studio | A |
| SandboxExecRunner | cowork | A |
| SandboxPolicy | agent-studio, cowork | A |
| SandboxRunner | cowork | A |
| ScanReport | - | I |
| ScopedPermission | cowork | A |
| ScopedPermissionEngine | cowork | A |
| ScopedPermissionError | cowork | A |
| SessionEventLog | agent-studio | A |
| Skill | agent-studio | A |
| SkillError | agent-studio | A |
| SkillRegistry | agent-studio | A |
| SpawnBrief | agent-studio | A |
| SpawnBriefError | agent-studio | A |
| SubagentRunner | agent-studio, cowork | A |
| SubagentSpec | agent-studio, cowork | A |
| SummaryInjector | agent-studio | A |
| TeamDefError | cowork | A |
| TeamDefinition | agent-studio, cowork | A |
| TeamMember | agent-studio, cowork | A |
| TeamMessage | agent-studio, cowork | A |
| TeamMessageError | cowork | A |
| TeamRuntime | agent-studio, cowork | A |
| TeamTask | agent-studio | A |
| TokenCounter | - | I |
| ToolFunnel | agent-studio, cowork, console | A |
| ToolPipeline | agent-studio | A |
| TopologyError | - | I |
| TopologySelector | - | I |
| TrajectoryRecord | agent-studio, cowork | A |
| TrajectorySchemaError | agent-studio | A |
| TrajectoryWriter | agent-studio | A |
| WorkerDelivery | agent-studio | A |
| bind_node_state | agent-studio | A |
| brief_from_event | agent-studio | A |
| cite_link | - | I |
| count_messages | - | I |
| extract_links | - | I |
| idempotency_key | - | I |
| mask_tools | agent-studio | A |
| normalize_record | agent-studio | A |
| parse_repair | agent-studio, cowork | A |
| parse_skill | agent-studio | A |
| scan_artifact | agent-studio, cowork | A |
| score_tool_risk | agent-studio | A |
| stamp_untrusted | agent-studio | A |
| validate_brief | agent-studio | A |
