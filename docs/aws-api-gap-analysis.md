# AWS API Gap Analysis — Bedrock Budgeteer

**Date:** 2026-04-03
**Scope:** Critical-path AWS API validation (Bedrock events, Pricing, IAM suspension, cost calculation)

## Executive Summary

Found **14 gaps** across 4 research streams: **3 BREAKING** (system silently misses usage), **7 STALE** (inaccurate cost numbers), **4 ENHANCEMENT** (nice-to-have improvements). The most critical finding is that the system doesn't track several new Bedrock API operations (InvokeModelWithBidirectionalStream, InvokeInlineAgent, async invocation APIs), and is missing pricing for Claude 4.5/4.6, Haiku 4.5, and Llama 4 models.

---

## Breaking Changes (must fix)

| # | Finding | Stream | Impact |
|---|---------|--------|--------|
| B1 | Missing EventBridge events: `InvokeModelWithBidirectionalStream` (full-duplex streaming) | Stream 1 | Usage from bidirectional streaming calls is not tracked at all |
| B2 | Missing EventBridge events: `InvokeInlineAgent` (inline agents) | Stream 1 | Inline agent invocations bypass budget tracking entirely |
| B3 | Missing EventBridge events: `StartAsyncInvoke`, `GetAsyncInvoke`, `ListAsyncInvokes` (async invocation) | Stream 1 | Async batch invocations not captured by event rules |

## Stale Data (should fix)

| # | Finding | Stream | Impact |
|---|---------|--------|--------|
| S1 | Missing fallback pricing: Claude Opus 4.5 ($5/$25 per 1M tokens) | Stream 2 | Falls back to default Sonnet pricing ($3/$15) — undercharges Opus 4.5 |
| S2 | Missing fallback pricing: Claude Opus 4.6 ($5/$25 per 1M tokens) | Stream 2 | Same as S1 |
| S3 | Missing fallback pricing: Claude Sonnet 4.5 ($3/$15 per 1M tokens) | Stream 2 | Falls back correctly by coincidence (default is Sonnet pricing) |
| S4 | Missing fallback pricing: Claude Sonnet 4.6 ($3/$15 per 1M tokens) | Stream 2 | Same as S3 |
| S5 | Missing fallback pricing: Claude Haiku 4.5 ($1/$5 per 1M tokens) | Stream 2 | Falls back to Sonnet pricing ($3/$15) — overcharges Haiku 4.5 |
| S6 | Missing fallback pricing: Llama 4 Scout and Maverick ($0.24/$0.97 per 1M for Maverick) | Stream 2 | Falls back to Sonnet pricing — grossly overcharges Llama 4 |
| S7 | Cache write pricing incorrect: system charges 1.0x input rate, actual is 1.25x (5-min TTL) or 2.0x (1-hour TTL) | Stream 4 | Undercharges cache creation by 20-50% |

## Enhancement Opportunities (nice to have)

| # | Finding | Stream | Impact |
|---|---------|--------|--------|
| E1 | Nova Reel video generation ($0.08/sec) not tracked | Stream 4 | Video generation usage not budget-tracked |
| E2 | Guardrail ApplyGuardrail pricing ($0.15/1K text units) not tracked | Stream 4 | Guardrail usage not budget-tracked |
| E3 | Extended thinking tokens billed as output tokens — system doesn't distinguish | Stream 4 | No impact on cost (billed same rate), but limits visibility |
| E4 | New Bedrock Mantle managed policies available (AmazonBedrockMantleFullAccess, etc.) | Stream 3 | Not relevant to current suspension mechanism, but may affect future access patterns |

---

## Detailed Findings

### Stream 1: Bedrock API & CloudTrail Events

#### New API Operations (not tracked by system)

**Bedrock Runtime:**
- **InvokeModelWithBidirectionalStream** — Full-duplex streaming for interactive applications (voice, real-time chat). Logged as CloudTrail DATA event. **Severity: BREAKING** — any usage through this API is completely invisible to budget tracking.
- **StartAsyncInvoke** — Submit async model invocation job, returns immediately with invocationArn. **Severity: BREAKING** — async invocations bypass real-time tracking.
- **GetAsyncInvoke** / **ListAsyncInvokes** — Poll async job status. **Severity: BREAKING** (StartAsyncInvoke is the cost-incurring call).

**Bedrock Agents Runtime:**
- **InvokeInlineAgent** — Configure and invoke an agent dynamically at runtime without pre-creating it. **Severity: BREAKING** — inline agent calls bypass budget tracking.
- **OptimizePrompt** — Optimize prompts for better model performance. **Severity: ENHANCEMENT** — low cost operation.

#### CloudTrail Event Classification Change
CloudTrail now classifies Bedrock events into **management events** (InvokeModel, Converse, ConverseStream, ListAsyncInvokes) and **data events** (InvokeModelWithBidirectionalStream, GetAsyncInvoke, StartAsyncInvoke, InvokeInlineAgent). Data events require explicit CloudTrail configuration to capture — the system's current CloudTrail trail may not capture data events unless `IncludeManagementEvents` and data event selectors are properly configured.

#### Event Schema Changes
- No breaking changes found to existing event schema for InvokeModel/Converse/ConverseStream.
- Extended thinking tokens appear in Converse API response under `usage.outputTokens` (not a separate field).

#### New Model ID Formats
- Claude 4.5/4.6 models use IDs like: `anthropic.claude-sonnet-4-5-*`, `anthropic.claude-opus-4-6-*`
- Llama 4 models: `meta.llama4-scout-*`, `meta.llama4-maverick-*`
- Cross-region prefixes continue same pattern: `us.anthropic.claude-*`, `us.meta.llama4-*`
- No breaking changes to `_resolve_model_id_from_arn()` — existing patterns handle these.

Sources:
- [CloudTrail logging for Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/logging-using-cloudtrail.html)
- [Bedrock Runtime API Reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_Operations_Amazon_Bedrock_Runtime.html)
- [InvokeModelWithBidirectionalStream](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_InvokeModelWithBidirectionalStream.html)
- [InvokeInlineAgent](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_InvokeInlineAgent.html)

---

### Stream 2: AWS Pricing API for Bedrock

#### Pricing API Format Changes
- No breaking changes found to `GetProducts` response schema. `ServiceCode=AmazonBedrock` still works.
- `terms.OnDemand.priceDimensions.pricePerUnit.USD` structure unchanged.
- No severity issues.

#### New Pricing Dimensions
- **Prompt caching TTL tiers**: 5-minute (1.25x write / 0.1x read) and 1-hour (2.0x write / 0.1x read). System only tracks cache read correctly (10%), but cache write is wrong (see S7).
- **Guardrail pricing**: $0.15 per 1K text units for content filters and denied topics.
- **Video generation**: Nova Reel at $0.08/second.
- **Batch inference**: Confirmed 50% discount vs on-demand.

#### Fallback Price Discrepancies

| Model ID | System Price (in/out per 1K) | Current Price (in/out per 1K) | Status |
|----------|------------------------------|-------------------------------|--------|
| Claude Opus 4 (`anthropic.claude-opus-4-20250115-v1:0`) | $0.015/$0.075 | $0.015/$0.075 | **OK** |
| Claude Opus 4.1 (`anthropic.claude-opus-4-1-20250115-v1:0`) | $0.015/$0.075 | $0.015/$0.075 | **OK** |
| Claude Sonnet 4 (`anthropic.claude-sonnet-4-20250115-v1:0`) | $0.003/$0.015 | $0.003/$0.015 | **OK** |
| Claude 3.5 Sonnet v2 (`anthropic.claude-3-5-sonnet-20241022-v2:0`) | $0.003/$0.015 | $0.006/$0.030 (extended access) | **STALE** — legacy price doubled Dec 2025 |
| Claude 3.5 Sonnet v1 (`anthropic.claude-3-5-sonnet-20240620-v1:0`) | $0.003/$0.015 | EOL March 2026 | **STALE** — model deprecated |
| Nova Micro/Lite/Pro/Premier | All correct | All correct | **OK** |

#### New Models Not in Fallbacks

| Model | Provider | Input Price (per 1K) | Output Price (per 1K) |
|-------|----------|---------------------|----------------------|
| Claude Opus 4.5 | Anthropic | $0.005 | $0.025 |
| Claude Opus 4.6 | Anthropic | $0.005 | $0.025 |
| Claude Sonnet 4.5 | Anthropic | $0.003 | $0.015 |
| Claude Sonnet 4.6 | Anthropic | $0.003 | $0.015 |
| Claude Haiku 4.5 | Anthropic | $0.001 | $0.005 |
| Llama 4 Scout | Meta | ~$0.00017 | ~$0.00069 |
| Llama 4 Maverick | Meta | $0.00024 | $0.00097 |

Sources:
- [AWS Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/)
- [Claude API Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [Bedrock Prompt Caching](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html)
- [Claude Sonnet 4.6 on Bedrock](https://aws.amazon.com/about-aws/whats-new/2026/02/claude-sonnet-4.6-available-in-amazon-bedrock/)
- [Claude Opus 4.6 on Bedrock](https://aws.amazon.com/about-aws/whats-new/2026/2/claude-opus-4.6-available-amazon-bedrock/)

---

### Stream 3: IAM Suspension Mechanism

#### AmazonBedrockLimitedAccess Policy Status
- **Exists: YES** — `arn:aws:iam::aws:policy/AmazonBedrockLimitedAccess` is still an active AWS managed policy.
- **Permissions**: Allows Bedrock API access including model invocation, guardrails, jobs, and KMS/networking/Marketplace operations.
- **Changes since mid-2025**: No breaking changes. Policy continues to be auto-attached to `BedrockAPIKey-*` IAM users created via Bedrock console.

#### Bedrock API Key User Management
- **Still uses `BedrockAPIKey-` prefix**: YES — Bedrock console still creates IAM users with this naming convention and attaches AmazonBedrockLimitedAccess.
- **No changes to provisioning flow**.

#### Better Alternatives Available
- **Bedrock Mantle**: New service with `AmazonBedrockMantleFullAccess`, `AmazonBedrockMantleReadOnly`, `AmazonBedrockMantleInferenceAccess` policies. Purpose unclear from available docs — **MONITOR** but no action needed.
- **No Bedrock-native budget controls** found. AWS Budgets doesn't have Bedrock-specific integration. No per-key throttling or quota mechanisms.
- The IAM policy detachment approach remains the best available mechanism.

#### IAM API Correctness
- `AttachUserPolicy` / `DetachUserPolicy` — still correct, no deprecations.
- `ListAttachedUserPolicies` — still correct for verification.
- No changes needed.

Sources:
- [AmazonBedrockLimitedAccess Policy Reference](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonBedrockLimitedAccess.html)
- [AWS Managed Policies for Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/security-iam-awsmanpol.html)
- [Securing Bedrock API Keys](https://aws.amazon.com/blogs/security/securing-amazon-bedrock-api-keys-best-practices-for-implementation-and-management/)

---

### Stream 4: Cost Calculation Logic

#### Cache Token Pricing
- **System assumption**: Cache read = 10% of input rate ✅ **CORRECT**
- **System assumption**: Cache creation = 1.0x input rate ❌ **INCORRECT**
- **Actual**: Cache write = 1.25x input rate (5-min TTL) or 2.0x input rate (1-hour TTL)
- **Impact**: System undercharges cache creation operations by 20-50%
- **Severity: STALE**

#### Extended Thinking / Reasoning Tokens
- **Supported on Bedrock**: YES (Claude models via Converse API)
- **Pricing**: Billed as output tokens (same rate)
- **Reported in events**: Under `usage.outputTokens` in Converse response
- **System handles this**: YES — output tokens include thinking tokens, cost is correct
- **Severity: ENHANCEMENT** (visibility only, not cost accuracy)

#### Image Generation Pricing

| Model | System Price | Current Price | Status |
|-------|-------------|---------------|--------|
| Stability SDXL | $0.036/image | $0.036/image | **OK** |
| Stability SD3 | $0.035/image | $0.035/image | **OK** |
| Stability Ultra | $0.06/image | $0.06/image | **OK** |
| Stability Core | $0.04/image | $0.04/image | **OK** |
| Titan Image Gen v1/v2 | $0.012/image | $0.012/image | **OK** |
| Nova Canvas | $0.04/image | $0.04-$0.08/image | **STALE** — resolution-dependent pricing now |

#### Video Generation
- **Nova Reel available**: YES, at $0.08/second of video
- **System handles this**: NO
- **Severity: ENHANCEMENT** — adds a new modality not currently budget-tracked

#### Agent/Flow/KB Pricing
- **Flows**: $0.035/1000 transitions — **CONFIRMED CORRECT** ✅
- **Agent pricing**: Token-based, same as underlying model — **CONFIRMED CORRECT** ✅
- **KB pricing**: No changes found — **OK** ✅

#### Batch Inference
- **Discount**: 50% of on-demand pricing — **CONFIRMED**
- **System applies discount**: NO — system uses standard pricing for batch jobs
- **Severity: STALE** — overcharges batch inference by 2x

Sources:
- [Bedrock Prompt Caching](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html)
- [1-hour cache TTL announcement](https://aws.amazon.com/about-aws/whats-new/2026/01/amazon-bedrock-one-hour-duration-prompt-caching/)
- [Extended Thinking on Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/claude-messages-extended-thinking.html)
- [Amazon Nova Pricing](https://aws.amazon.com/nova/pricing/)
- [Bedrock Guardrails pricing reduction](https://aws.amazon.com/about-aws/whats-new/2024/12/amazon-bedrock-guardrails-reduces-pricing-85-percent/)
