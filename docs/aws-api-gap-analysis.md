# AWS API Gap Analysis — Bedrock Budgeteer

**Date:** 2026-04-03
**Scope:** Critical-path AWS API validation (Bedrock events, Pricing, IAM suspension, cost calculation)
**Updated:** Merged findings from parallel research agents + direct web research

## Executive Summary

Found **22 gaps** across 4 research streams: **7 BREAKING** (system silently misses usage or produces wrong results), **9 STALE** (inaccurate cost numbers or missing models), **6 ENHANCEMENT** (nice-to-have improvements). The most critical findings are:

1. CloudTrail data events may not be captured at all — several tracked operations (InvokeAgent, InvokeFlow, Retrieve, RetrieveAndGenerate) are now classified as data events requiring explicit advanced event selectors
2. New API operations not tracked: InvokeModelWithBidirectionalStream, InvokeInlineAgent, RetrieveAndGenerateStream, StartAsyncInvoke
3. Cross-region model ID prefix regex is incomplete (missing `global.`, `apac.`, `au.`, `ca.`, `jp.` prefixes)
4. Missing pricing for Claude 4.5/4.6, Haiku 4.5, Llama 4, and 10+ new providers on Bedrock

---

## Breaking Changes (must fix)

| # | Finding | Stream | Impact |
|---|---------|--------|--------|
| B1 | **CloudTrail data events not captured**: InvokeAgent, InvokeFlow, Retrieve, RetrieveAndGenerate are DATA events requiring advanced event selectors. Current CloudTrail trail may only capture management events. | Stream 1 | ALL agent/flow/KB tracking may be silently broken |
| B2 | Missing event: `InvokeModelWithBidirectionalStream` (full-duplex streaming for Nova Sonic speech) | Stream 1 | Bidirectional streaming usage invisible to budget tracking |
| B3 | Missing event: `InvokeInlineAgent` (inline agents). Uses `foundationModel` field instead of `modelId` | Stream 1 | Inline agent invocations bypass budget tracking entirely |
| B4 | Missing event: `RetrieveAndGenerateStream` (streaming RAG) | Stream 1 | Streaming KB queries not tracked |
| B5 | Missing event: `StartAsyncInvoke` (async model invocation) | Stream 1 | Async invocations not captured |
| B6 | Cross-region prefix regex incomplete: missing `global.`, `apac.`, `au.`, `ca.`, `jp.`, `us-gov.` prefixes in `_resolve_model_id_from_arn()` | Stream 1 | Models invoked via global/regional inference profiles won't resolve correctly for pricing |
| B7 | `_parse_pricing_response()` doesn't filter by model ID — returns last matching price for ANY model in region | Stream 2 | Pricing API path returns wrong prices; system survives on DynamoDB cache/fallbacks only |

## Stale Data (should fix)

| # | Finding | Stream | Impact |
|---|---------|--------|--------|
| S1 | Missing fallback pricing: Claude Opus 4.5 ($0.005/$0.025 per 1K) | Stream 2 | Falls back to default $0.003/$0.015 — undercharges Opus 4.5 |
| S2 | Missing fallback pricing: Claude Opus 4.6 ($0.005/$0.025 per 1K) | Stream 2 | Same as S1 |
| S3 | Missing fallback pricing: Claude Sonnet 4.5/4.6 ($0.003/$0.015 per 1K) | Stream 2 | Falls back correctly by coincidence |
| S4 | Missing fallback pricing: Claude Haiku 4.5 ($0.001/$0.005 per 1K) | Stream 2 | Falls back to Sonnet — overcharges by 3x |
| S5 | Missing fallback pricing: Llama 4 Scout/Maverick ($0.00024/$0.00097 per 1K for Maverick) | Stream 2 | Falls back to Sonnet — overcharges by 12x |
| S6 | Missing providers in model ID regex: deepseek, google, qwen, writer, twelvelabs, luma, nvidia, openai | Stream 1 | Inference profile ARNs for new providers won't resolve |
| S7 | Cache write pricing incorrect: system charges 1.0x input rate, actual is 1.25x (5-min TTL) or 2.0x (1-hour TTL) | Stream 4 | Undercharges cache creation by 20-50% |
| S8 | Claude 3.5 Sonnet v1 deprecated (EOL March 2026), v2 price doubled to $0.006/$0.030 in extended access | Stream 2 | Stale pricing for legacy models |
| S9 | Batch inference 50% discount not applied by system | Stream 4 | Overcharges batch jobs by 2x |

## Enhancement Opportunities (nice to have)

| # | Finding | Stream | Impact |
|---|---------|--------|--------|
| E1 | Nova Reel video generation ($0.08/sec) not tracked | Stream 4 | Video usage not budget-tracked |
| E2 | Guardrail ApplyGuardrail pricing ($0.15/1K text units) not tracked | Stream 4 | Guardrail costs not tracked |
| E3 | Extended thinking tokens billed as output tokens — no cost impact but limits visibility | Stream 4 | Cosmetic — no cost difference |
| E4 | Short-term API keys (up to 12hrs) bypass suspension until expiry | Stream 3 | Time-limited risk window |
| E5 | `bedrock:CallWithBearerToken` deny policy as supplementary suspension mechanism | Stream 3 | More surgical alternative |
| E6 | Async flow execution APIs (StartFlowExecution etc.) in preview | Stream 1 | Future-proofing |

---

## Detailed Findings

### Stream 1: Bedrock API & CloudTrail Events

#### CRITICAL: Data Events vs Management Events

CloudTrail now classifies Bedrock events into two categories:

**Management events** (captured by default):
- InvokeModel, InvokeModelWithResponseStream, Converse, ConverseStream, ListAsyncInvokes

**Data events** (require advanced event selectors):
- InvokeModelWithBidirectionalStream (`AWS::Bedrock::Model`)
- StartAsyncInvoke, GetAsyncInvoke (`AWS::Bedrock::Model`)
- InvokeAgent, InvokeInlineAgent (`AWS::Bedrock::Agent` / `AWS::Bedrock::InlineAgent`)
- InvokeFlow, StartFlowExecution (`AWS::Bedrock::Flow`)
- Retrieve, RetrieveAndGenerate, RetrieveAndGenerateStream (`AWS::Bedrock::KnowledgeBase`)
- ApplyGuardrail (`AWS::Bedrock::Guardrail`)

**Impact:** The system's CloudTrail trail must have advanced event selectors configured for these resource types, or the EventBridge rules will never fire for agent/flow/KB events.

#### New API Operations Not Tracked

| Operation | Service | Type | Severity |
|-----------|---------|------|----------|
| InvokeModelWithBidirectionalStream | bedrock-runtime | Data event | BREAKING |
| StartAsyncInvoke | bedrock-runtime | Data event | BREAKING |
| InvokeInlineAgent | bedrock-agent-runtime | Data event | BREAKING |
| RetrieveAndGenerateStream | bedrock-agent-runtime | Data event | BREAKING |
| OptimizePrompt | bedrock-agent-runtime | Data event | STALE |
| Rerank | bedrock-agent-runtime | Data event | STALE |
| GenerateQuery | bedrock-agent-runtime | Data event | STALE |
| StartFlowExecution | bedrock-agent-runtime | Data event | ENHANCEMENT |

#### Cross-Region Prefix Regex Gaps

Current regex handles: `us.`, `eu.`, `ap.`
Missing prefixes: `global.`, `apac.`, `au.`, `ca.`, `jp.`, `us-gov.`

#### New Providers on Bedrock (not in model ID regex)

deepseek, google, qwen, writer, twelvelabs, luma, moonshotai, nvidia, openai, zai

Sources:
- [CloudTrail Logging for Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/logging-using-cloudtrail.html)
- [Bedrock Runtime API Reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_Operations_Amazon_Bedrock_Runtime.html)
- [Agents Runtime API Reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_Operations_Agents_for_Amazon_Bedrock_Runtime.html)

---

### Stream 2: AWS Pricing API for Bedrock

#### Pricing API Format
- No breaking changes to `GetProducts` response schema
- **BUG: `_parse_pricing_response()` doesn't filter by model ID** — iterates all PriceList items and returns the last matching input/output rates. This means the Pricing API path is effectively broken and the system relies entirely on DynamoDB cache + fallback pricing.

#### New Models Not in Fallbacks

| Model | Provider | Input (per 1K) | Output (per 1K) |
|-------|----------|----------------|-----------------|
| Claude Opus 4.5 | Anthropic | $0.005 | $0.025 |
| Claude Opus 4.6 | Anthropic | $0.005 | $0.025 |
| Claude Sonnet 4.5 | Anthropic | $0.003 | $0.015 |
| Claude Sonnet 4.6 | Anthropic | $0.003 | $0.015 |
| Claude Haiku 4.5 | Anthropic | $0.001 | $0.005 |
| Llama 4 Scout | Meta | ~$0.00017 | ~$0.00069 |
| Llama 4 Maverick | Meta | $0.00024 | $0.00097 |
| Mistral Large 2 (2407) | Mistral | $0.003 | $0.009 |
| DeepSeek R1 | DeepSeek | TBD | TBD |

#### Cache Pricing Structure
- 5-min TTL: Write 1.25x, Read 0.1x input rate
- 1-hour TTL: Write 2.0x, Read 0.1x input rate
- System currently: Write 1.0x (wrong), Read 0.1x (correct)

Sources:
- [AWS Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/)
- [Bedrock Prompt Caching](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html)

---

### Stream 3: IAM Suspension Mechanism

#### AmazonBedrockLimitedAccess Policy
- **Exists: YES** — active, current version v7 (updated March 2026)
- **Permissions expanded** to include Bedrock Mantle and automated reasoning
- **BedrockAPIKey- prefix**: Still used by Bedrock console for long-term API key users
- **No Bedrock-native budget controls exist** — custom solution still necessary

#### New Considerations
- **Short-term keys** (up to 12 hours) inherit creating principal's permissions, not the IAM user policy — suspended user's short-term keys valid until expiry
- **`bedrock:CallWithBearerToken` deny** could be a more surgical suspension approach
- IAM APIs (Attach/Detach/ListAttachedUserPolicies) unchanged, no deprecations

Sources:
- [AmazonBedrockLimitedAccess Reference](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonBedrockLimitedAccess.html)
- [Securing Bedrock API Keys](https://aws.amazon.com/blogs/security/securing-amazon-bedrock-api-keys-best-practices-for-implementation-and-management/)

---

### Stream 4: Cost Calculation Logic

#### Cache Pricing
- Read: 10% of input ✅ CORRECT
- Write: 1.0x input ❌ Should be 1.25x (5-min) or 2.0x (1-hour)

#### Extended Thinking
- Billed as output tokens — system handles correctly (no separate rate)

#### Image Pricing
- All image model prices confirmed accurate
- Nova Canvas now has resolution-dependent tiers ($0.04-$0.08)

#### Agent/Flow/KB Pricing
- Flows $0.035/1K transitions ✅ CONFIRMED
- Agent token-based ✅ CONFIRMED
- KB pricing ✅ UNCHANGED

#### Batch Inference
- 50% discount confirmed — system doesn't apply it (overcharges 2x)

Sources:
- [Bedrock Prompt Caching](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html)
- [Amazon Nova Pricing](https://aws.amazon.com/nova/pricing/)
