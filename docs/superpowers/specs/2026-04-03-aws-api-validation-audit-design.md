# AWS API Validation Audit — Design Spec

**Date:** 2026-04-03
**Status:** Approved
**Scope:** Validate Bedrock Budgeteer's critical-path AWS API calls and logic against current AWS documentation, then fix all discrepancies.

## Problem Statement

Bedrock Budgeteer was built against AWS APIs as of mid-2025. AWS Bedrock is a rapidly evolving service — new models, new invocation patterns, pricing changes, and API updates ship regularly. The system's correctness depends on accurate assumptions about CloudTrail event formats, Pricing API responses, IAM policy behavior, and cost calculation logic. This audit validates those assumptions and fixes any drift.

## Scope

### In Scope (Critical Path)

Four areas where AWS changes directly affect budget enforcement correctness:

1. **Bedrock API & CloudTrail Events** — Event names, schemas, new operations
2. **AWS Pricing API for Bedrock** — Response format, new pricing dimensions, model coverage
3. **IAM Suspension Mechanism** — `AmazonBedrockLimitedAccess` policy, attach/detach semantics
4. **Cost Calculation Logic** — Token pricing, image/video pricing, new modalities, model families

### Out of Scope (Stable Services)

These AWS services have stable APIs and are not audited unless a critical-path fix requires changes:

- SNS, CloudWatch, Firehose, Lambda, DynamoDB, S3, SSM, Step Functions, SQS, CloudTrail (infrastructure), EventBridge (infrastructure)

## Approach

### Phase 1: Parallel Research

Four parallel research agents, each investigating current AWS documentation for their area:

#### Stream 1: Bedrock API & CloudTrail Events
- Current CloudTrail event names emitted by Bedrock
- Compare against system's EventBridge rules which filter on: `InvokeModel`, `Converse`, `ConverseStream`, `InvokeAgent`, `InvokeFlow`, `Retrieve`, `RetrieveAndGenerate`, `CreateModelInvocationJob`, `ApplyGuardrail`
- New Bedrock API operations the system doesn't track
- CloudTrail event schema changes (request/response fields parsed by usage_calculator)
- New model families or inference profiles affecting model ID format in events

#### Stream 2: AWS Pricing API for Bedrock
- `GetProducts` with `ServiceCode=AmazonBedrock` response schema
- New pricing dimensions (per-request pricing, cached token pricing, new modalities)
- Models now in the Pricing API that were previously hardcoded as static fallbacks
- Attribute naming changes (`inputTokenPrice`, `outputTokenPrice`, etc.)

#### Stream 3: IAM Suspension Mechanism
- `AmazonBedrockLimitedAccess` managed policy — existence and permission scope
- Better mechanisms for Bedrock access control (SCPs, resource policies, Bedrock-native throttling)
- `AttachUserPolicy`/`DetachUserPolicy` correctness for API key users

#### Stream 4: Cost Calculation Logic
- pricing_calculator.py accuracy against current Bedrock pricing
- Token counting logic for current model families (Claude 4.x, Nova, Titan, etc.)
- Image/video generation pricing dimensions
- Batch inference discount assumptions

**Output:** Unified gap analysis document listing every discrepancy, categorized by severity.

### Phase 2: Gap Analysis Review (Checkpoint)

Present consolidated findings to user before any code changes. User approves, reorders, or deprioritizes gaps. No implementation begins until this checkpoint passes.

### Phase 3: Implementation (Priority-Ordered)

#### Priority 1: Breaking Changes
Gaps where the system silently misses usage or produces incorrect results:
- New Bedrock API event names missing from EventBridge rules
- CloudTrail event schema changes breaking usage_calculator parsing
- Pricing API response format changes breaking pricing_manager

#### Priority 2: Stale Data
System works but produces inaccurate cost numbers:
- Outdated static pricing fallbacks in pricing_calculator.py
- Missing model families (new Claude, Nova, Titan variants)
- New pricing dimensions not captured (cached tokens, per-request fees)

#### Priority 3: Mechanism Improvements
System works correctly but could be better:
- Bedrock-native access control alternatives to IAM policy detachment
- New invocation patterns that should be budget-tracked
- Cross-region inference profile cost attribution

### Phase 4: Validation

- Run full unit test suite (`python -m pytest tests/unit/ -v`)
- Verify CDK synth produces valid templates (`cdk synth`)
- Confirm no regressions in existing functionality

## Testing Strategy

- Update unit tests for any changed event schemas or pricing logic
- Add test cases for newly supported Bedrock API events
- Add test cases for new pricing dimensions
- Verify CDK assertions still pass after construct changes

## Deliverables

1. **Gap analysis document** — Committed to `docs/` with full findings
2. **Updated code** — All approved fixes applied
3. **Updated tests** — Coverage for new and changed behavior
4. **Updated CHANGELOG.md** — Documenting what changed and why

## Risks

- **AWS docs may be incomplete** — Some Bedrock features ship before documentation is fully updated. Mitigation: cross-reference docs with AWS blog posts and SDK changelogs.
- **Pricing data lag** — New models may not appear in the Pricing API for weeks after launch. Mitigation: maintain static fallback strategy for new models.
- **Managed policy changes** — If `AmazonBedrockLimitedAccess` was modified or deprecated, the suspension mechanism needs redesign. Mitigation: verify early in research phase.

## Decision Log

| Decision | Rationale |
|----------|-----------|
| Focus on 4 critical-path areas only | Stable AWS services (DynamoDB, SNS, etc.) haven't changed APIs meaningfully |
| Parallel research before any fixes | Catches cross-cutting issues early, enables smart fix ordering |
| Checkpoint before implementation | User controls which gaps get fixed and in what order |
| Priority ordering: breaking > stale > improvements | Correctness first, accuracy second, enhancements third |
