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

- Exports: 186  |  Adopted: 71  |  **Rate: 38.2%** (target 80%, NOT met)
- Zero-consumer names (115): AdapterHost, ApprovalDecision, CODE_MODE_SYSTEM_PROMPT, CacheWarmingGate, CheckpointError, CodeExecutor, CodeModeError, CodeModeMetrics, CodeModeTurn, CodeModeTurnResult, CompactionArchive, DEFAULT_MAX_BYTES_CAP, DanglingLinkError, Deadline, DeadlineExceeded, Effect, EffortTierConfig, FailureAnalyzer, FailureVerdict, HIGH_RISK_NODES, HandoffVerification, HandoffVerifyError, HeuristicTokenCounter, HumanGateError, HumanQuestion, KERNEL_VERSION, LOOP_SURFACES, LogSchemaError, LoopDetector, MASTMode, MAST_CLUSTERS, MEMBER_CONTEXT_CAP_BYTES, MemoryBridge, MemorySink, MemorySource, MonotonicGuard, NodeContext, NodeResult, NodeStateBinder, PERMISSIVENESS, ParamCoercionError, PermissionLevel, PipelineBlocked, PipelineOutcome, PrefixStabilityTracker, PrefixTelemetry, ProviderAdapter, ProviderSessionEvent, ProviderSessionState, ReceiptReplayed, ReconcileReport, ReplyValidationError, RiskIntel, RiskIntelClient, RuntimeNotReady, SCOPED_DECISIONS, STATUS_ACTIVE, STATUS_ARCHIVED, STATUS_CANARY, SandboxRunnerUnavailable, ScanReport, SegmentBudget, SegmentError, SegmentPolicy, SessionEvent, SessionState, SkillCase, SkillLibrary, SkillScanError, SkillVersion, SubagentResult, SubagentSession, SubprocessSessionRuntime, TEAM_SPEC_CAP_BYTES, TOOL_DESTRUCTIVE_TABLE, TRAJECTORY_DISCARD_REASONS, TRAJECTORY_EVENTS, TeamStateError, TokenCounter, TokenLedger, ToolAvailabilityState, ToolResult, TrajectoryReader, TransientError, UnknownStubError, WarmDecision, assert_stable_prefix, check_append_only, check_runner_conformance, cite_link, claims_for_transport, cluster_of, coalesce_retry, coerce_params, count_messages, default_registry, extract_links, idempotency_key, inject_code_mode_messages, ledger_for_transport, map_risk_to_tier, mark_discardable, parse_code_block, read_segment, register, rehydrate, render_segment_result, render_stubs, run_node, run_with_retry, segment_header, stamp_untrusted, validate_reply, verify_handoff, verify_spawn_brief

| name | consumers | tier |
|---|---|---|
| AdapterHost | - | B |
| ApprovalDecision | - | B |
| ApprovalGate | cowork | A |
| ArtifactQuarantine | cowork | A |
| ArtifactStore | agent-studio | A |
| ArtifactTools | agent-studio | A |
| BackgroundPool | agent-studio | A |
| BaseNode | cowork | A |
| CJKAwareHeuristicTokenCounter | agent-studio | A |
| CODE_MODE_SYSTEM_PROMPT | - | B |
| CacheTelemetry | agent-studio | A |
| CacheWarmingGate | - | B |
| CheckpointError | - | B |
| CheckpointState | agent-studio, cowork | A |
| CheckpointStore | agent-studio, cowork | A |
| CodeExecutor | - | B |
| CodeModeError | - | B |
| CodeModeMetrics | - | B |
| CodeModeTurn | - | B |
| CodeModeTurnResult | - | B |
| CompactionArchive | - | B |
| CompactionConfig | agent-studio, cowork, console | A |
| Compactor | agent-studio, cowork, console | A |
| ConfirmationPolicy | agent-studio | A |
| DEFAULT_MAX_BYTES_CAP | - | B |
| DanglingLinkError | - | B |
| Deadline | - | B |
| DeadlineExceeded | - | B |
| Effect | - | B |
| EffortTierConfig | - | B |
| ExecutionTier | agent-studio, cowork | A |
| FailureAnalyzer | - | B |
| FailureVerdict | - | B |
| HIGH_RISK_NODES | - | B |
| HandoffVerification | - | B |
| HandoffVerifyError | - | B |
| HeuristicTokenCounter | - | B |
| HookConfig | agent-studio, cowork | A |
| HookEngine | agent-studio, cowork | A |
| HookResult | agent-studio, cowork | A |
| HumanGate | agent-studio, cowork | A |
| HumanGateError | - | B |
| HumanQuestion | - | B |
| JSONRepairError | agent-studio, cowork | A |
| KERNEL_VERSION | - | B |
| LLMFunnel | agent-studio, cowork, console | A |
| LOOP_SURFACES | - | B |
| LifecycleBus | agent-studio, cowork, console | A |
| LogSchemaError | - | B |
| LoopDetector | - | B |
| MASTMode | - | B |
| MAST_CLUSTERS | - | B |
| MEMBER_CONTEXT_CAP_BYTES | - | B |
| MSG_TYPES | cowork | A |
| MemoryBridge | - | B |
| MemorySink | - | B |
| MemorySource | - | B |
| MonotonicGuard | - | B |
| NodeContext | - | B |
| NodeRegistry | cowork | A |
| NodeRegistryError | cowork | A |
| NodeResult | - | B |
| NodeStateBinder | - | B |
| OutboxStore | agent-studio, cowork | A |
| PERMISSIVENESS | - | B |
| ParallelTeam | agent-studio, cowork | A |
| ParamCoercionError | - | B |
| PermissionDecision | agent-studio, cowork | A |
| PermissionEngine | agent-studio, cowork, console | A |
| PermissionLevel | - | B |
| PermissionMode | agent-studio, cowork | A |
| PermissionRule | agent-studio, cowork, console | A |
| PipelineBlocked | - | B |
| PipelineOutcome | - | B |
| Playbook | agent-studio | A |
| PlaybookOp | agent-studio | A |
| PrefixStabilityTracker | - | B |
| PrefixTelemetry | - | B |
| ProviderAdapter | - | B |
| ProviderSessionEvent | - | B |
| ProviderSessionState | - | B |
| ReceiptCache | cowork | A |
| ReceiptReplayed | - | B |
| ReconcileReport | - | B |
| ReplyValidationError | - | B |
| RetryPolicy | agent-studio | A |
| RiskIntel | - | B |
| RiskIntelClient | - | B |
| RuntimeNotReady | - | B |
| SCOPED_DECISIONS | - | B |
| STATUS_ACTIVE | - | B |
| STATUS_ARCHIVED | - | B |
| STATUS_CANARY | - | B |
| SandboxExecRunner | cowork | A |
| SandboxPolicy | agent-studio, cowork | A |
| SandboxRunner | cowork | A |
| SandboxRunnerUnavailable | - | B |
| ScanReport | - | B |
| ScopedPermission | cowork | A |
| ScopedPermissionEngine | cowork | A |
| ScopedPermissionError | cowork | A |
| SegmentBudget | - | B |
| SegmentError | - | B |
| SegmentPolicy | - | B |
| SessionEvent | - | B |
| SessionEventLog | agent-studio | A |
| SessionState | - | B |
| Skill | agent-studio | A |
| SkillCase | - | B |
| SkillError | agent-studio | A |
| SkillLibrary | - | B |
| SkillRegistry | agent-studio | A |
| SkillScanError | - | B |
| SkillVersion | - | B |
| SpawnBrief | agent-studio | A |
| SpawnBriefError | agent-studio | A |
| SubagentResult | - | B |
| SubagentRunner | agent-studio, cowork | A |
| SubagentSession | - | B |
| SubagentSpec | agent-studio, cowork | A |
| SubprocessSessionRuntime | - | B |
| SummaryInjector | agent-studio | A |
| TEAM_SPEC_CAP_BYTES | - | B |
| TOOL_DESTRUCTIVE_TABLE | - | B |
| TRAJECTORY_DISCARD_REASONS | - | B |
| TRAJECTORY_EVENTS | - | B |
| TeamDefError | cowork | A |
| TeamDefinition | agent-studio, cowork | A |
| TeamMember | agent-studio, cowork | A |
| TeamMessage | agent-studio, cowork | A |
| TeamMessageError | cowork | A |
| TeamRuntime | agent-studio, cowork | A |
| TeamStateError | - | B |
| TeamTask | agent-studio | A |
| TokenCounter | - | B |
| TokenLedger | - | B |
| ToolAvailabilityState | - | B |
| ToolFunnel | agent-studio, cowork, console | A |
| ToolPipeline | agent-studio | A |
| ToolResult | - | B |
| TrajectoryReader | - | B |
| TrajectoryRecord | agent-studio, cowork | A |
| TrajectorySchemaError | agent-studio | A |
| TrajectoryWriter | agent-studio | A |
| TransientError | - | B |
| UnknownStubError | - | B |
| WarmDecision | - | B |
| WorkerDelivery | agent-studio | A |
| assert_stable_prefix | - | B |
| bind_node_state | agent-studio | A |
| brief_from_event | agent-studio | A |
| check_append_only | - | B |
| check_runner_conformance | - | B |
| cite_link | - | B |
| claims_for_transport | - | B |
| cluster_of | - | B |
| coalesce_retry | - | B |
| coerce_params | - | B |
| count_messages | - | B |
| default_registry | - | B |
| extract_links | - | B |
| idempotency_key | - | B |
| inject_code_mode_messages | - | B |
| ledger_for_transport | - | B |
| map_risk_to_tier | - | B |
| mark_discardable | - | B |
| mask_tools | agent-studio | A |
| normalize_record | agent-studio | A |
| parse_code_block | - | B |
| parse_repair | agent-studio, cowork | A |
| parse_skill | agent-studio | A |
| read_segment | - | B |
| register | - | B |
| rehydrate | - | B |
| render_segment_result | - | B |
| render_stubs | - | B |
| run_node | - | B |
| run_with_retry | - | B |
| scan_artifact | cowork | A |
| score_tool_risk | agent-studio | A |
| segment_header | - | B |
| stamp_untrusted | - | B |
| validate_brief | agent-studio | A |
| validate_reply | - | B |
| verify_handoff | - | B |
| verify_spawn_brief | - | B |
