# AWS API Validation Audit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate Bedrock Budgeteer's critical-path AWS API calls against current AWS documentation and fix all discrepancies.

**Architecture:** Four parallel research streams investigate Bedrock CloudTrail events, Pricing API, IAM suspension mechanism, and cost calculation logic. Findings are consolidated into a gap analysis, reviewed by user, then fixed in priority order (breaking > stale > improvements). All fixes include test updates.

**Tech Stack:** Python 3.x, AWS CDK, boto3, moto (test mocking), pytest

---

## File Map

Files that will be **read during research** (no changes until Phase 3):

| File | Responsibility |
|------|---------------|
| `app/app/constructs/event_ingestion.py` | EventBridge rules, CloudTrail event patterns |
| `app/app/constructs/lambda_functions/usage_calculator.py` | Bedrock event processing, cost calculation, token tracking |
| `app/app/constructs/shared/pricing_calculator.py` | Pricing lookup, static fallbacks, cache token pricing |
| `app/app/constructs/lambda_functions/user_setup.py` | IAM event handling for Bedrock API keys |
| `app/app/constructs/workflow_lambda_functions/iam_utilities.py` | Suspension/restoration via AmazonBedrockLimitedAccess policy |
| `app/app/constructs/workflow_orchestration.py` | Step Functions IAM permissions |
| `app/app/constructs/core_processing.py` | Lambda function definitions, event source mappings |

Files that **will be created**:

| File | Responsibility |
|------|---------------|
| `docs/aws-api-gap-analysis.md` | Unified gap analysis from all 4 research streams |

Files that **may be modified** (pending gap analysis findings):

| File | Responsibility |
|------|---------------|
| `app/app/constructs/event_ingestion.py` | Add new Bedrock event names to EventBridge rules |
| `app/app/constructs/lambda_functions/usage_calculator.py` | Handle new event schemas, new API operations |
| `app/app/constructs/shared/pricing_calculator.py` | Update fallback prices, add new models, new pricing dimensions |
| `app/app/constructs/workflow_lambda_functions/iam_utilities.py` | Update suspension mechanism if needed |
| `app/tests/unit/test_core_processing.py` | Update tests for changed event handling |
| `app/tests/unit/test_integration.py` | Update EventBridge rule assertions |
| `CHANGELOG.md` | Document changes |

---

## Phase 1: Parallel Research (Tasks 1-4)

These 4 tasks run **in parallel**. Each produces a section of the gap analysis.

### Task 1: Research Bedrock API & CloudTrail Events

**Goal:** Identify new Bedrock API operations and CloudTrail event schema changes since mid-2025.

**Files to reference:**
- Read: `app/app/constructs/event_ingestion.py` (lines 150-210 for EventBridge rule definitions)
- Read: `app/app/constructs/lambda_functions/usage_calculator.py` (event parsing logic)

- [ ] **Step 1: Search AWS docs for current Bedrock CloudTrail event names**

Research the following using web search and AWS documentation:
- Current list of Bedrock API actions logged by CloudTrail (https://docs.aws.amazon.com/bedrock/latest/userguide/logging-using-cloudtrail.html)
- Any new Bedrock Runtime API operations added since August 2025
- Any new Bedrock Agents Runtime API operations
- Changes to `bedrock.amazonaws.com` and `bedrock-runtime.amazonaws.com` event sources in CloudTrail

The system currently tracks these event names in EventBridge rules:
```
# BedrockUsageRule (source: aws.bedrock, eventSource: bedrock.amazonaws.com)
InvokeModel, InvokeModelWithResponseStream, Converse, ConverseStream,
GetFoundationModel, ListFoundationModels

# BedrockAgentsRule (sources: bedrock-agent-runtime, bedrock-agent, bedrock)
InvokeAgent, InvokeFlow, Retrieve, RetrieveAndGenerate
```

Document any new operations NOT in the above lists.

- [ ] **Step 2: Check CloudTrail event schema for Bedrock Runtime APIs**

Research whether the CloudTrail event detail structure has changed for:
- `requestParameters` fields for InvokeModel/Converse (model ID location, request body fields)
- `responseElements` fields (token counts, usage metadata)
- `userIdentity` structure changes
- New fields added (e.g., inference profile ARN, guardrail ID, reasoning/thinking tokens)

The usage_calculator currently extracts:
```python
# From CloudTrail detail:
detail.get('requestParameters', {}).get('modelId')
detail.get('requestParameters', {}).get('body')  # for InvokeModel
detail.get('responseElements', {}).get('usage', {})  # for Converse
detail.get('userIdentity', {}).get('principalId')  # for attribution
```

Document any schema changes that would affect these extractions.

- [ ] **Step 3: Check for new model ID formats**

Research whether new Bedrock model IDs follow different patterns:
- Cross-region inference profile ARN format changes
- New model provider prefixes (beyond anthropic, amazon, meta, mistral, cohere, ai21, stability)
- Application inference profile ID format

The system resolves model IDs via `_resolve_model_id_from_arn()` which handles:
```python
# Patterns currently supported:
# arn:aws:bedrock:{region}::foundation-model/{model_id}
# arn:aws:bedrock:{region}:{account}:inference-profile/{profile_id}
# {region_prefix}.{provider}.{model_name}  (e.g., us.anthropic.claude-sonnet-4-...)
# Direct model ID (e.g., anthropic.claude-3-sonnet-20240229-v1:0)
```

- [ ] **Step 4: Document findings for Stream 1**

Write findings in this format:
```markdown
## Stream 1: Bedrock API & CloudTrail Events

### New API Operations (not tracked by system)
- [operation name] — [what it does] — [severity: BREAKING/STALE/ENHANCEMENT]

### Event Schema Changes
- [field change] — [impact on usage_calculator] — [severity]

### New Model ID Formats
- [new format] — [impact on _resolve_model_id_from_arn()] — [severity]
```

---

### Task 2: Research AWS Pricing API for Bedrock

**Goal:** Verify Pricing API response format and identify new pricing dimensions.

**Files to reference:**
- Read: `app/app/constructs/shared/pricing_calculator.py` (full file — fallback prices and API parsing)

- [ ] **Step 1: Research current Pricing API response format for Bedrock**

Research the following:
- `GetProducts` with `ServiceCode=AmazonBedrock` — current response schema
- Whether `productFamily` values have changed (system filters on `'Bedrock Model Inference'`)
- Whether `usageType` and `operation` attribute names have changed
- Whether pricing is still under `terms.OnDemand` with `priceDimensions` containing `pricePerUnit.USD`

The system's `_parse_pricing_response()` currently expects:
```python
# For each item in PriceList (JSON strings):
price_item['product']['attributes']['usageType']
price_item['product']['attributes']['operation']
price_item['terms']['OnDemand'][term_key]['priceDimensions'][dim_key]['pricePerUnit']['USD']
price_item['terms']['OnDemand'][term_key]['priceDimensions'][dim_key]['unit']
price_item['terms']['OnDemand'][term_key]['priceDimensions'][dim_key]['description']
```

Document any format changes.

- [ ] **Step 2: Research new pricing dimensions**

Check whether Bedrock now has pricing dimensions not captured by the system:
- **Cached token pricing** — system currently hardcodes cache read at 10% of input rate. Is there an official cache pricing dimension?
- **Per-request fees** — any base fee per API call?
- **Reasoning/thinking token pricing** — do extended thinking tokens have separate pricing?
- **Video generation pricing** — Amazon Nova Reel or other video models
- **Audio generation pricing** — any new audio modalities
- **Guardrail pricing** — per-assessment fees for ApplyGuardrail

- [ ] **Step 3: Cross-reference fallback pricing table against current Bedrock pricing page**

The system has ~60 hardcoded model prices in `_get_fallback_pricing()`. Research current Bedrock pricing (https://aws.amazon.com/bedrock/pricing/) and identify:
- Models with **changed prices** (input or output rate differs)
- Models **missing from fallbacks** (new models not in the table)
- Models in fallbacks that are **deprecated/removed** from Bedrock

Key models to verify:
```
# Claude family: 3-opus, 3-sonnet, 3-haiku, 3.5-sonnet (v1+v2), 3.5-haiku,
#   opus-4, opus-4-1, sonnet-4, sonnet-4-long-context, claude-sonnet-4-20250514
# Nova family: micro, lite, pro, premier, canvas
# Titan: text-express, text-lite, text-premier, embed-text v1/v2
# Meta Llama: 3-8b, 3-70b, 3.1-8b, 3.1-70b, 3.1-405b, 3.2-90b
# Mistral: 7b, mixtral-8x7b, large-2402
# Cohere: command-r, command-r-plus, embed-english
# AI21: jamba-1.5-mini, jamba-1.5-large
# Image: stability SDXL/SD3/ultra/core, titan-image v1/v2, nova-canvas
```

- [ ] **Step 4: Document findings for Stream 2**

Write findings in this format:
```markdown
## Stream 2: AWS Pricing API for Bedrock

### Pricing API Format Changes
- [change] — [impact on _parse_pricing_response()] — [severity]

### New Pricing Dimensions
- [dimension] — [description] — [severity: BREAKING/STALE/ENHANCEMENT]

### Fallback Price Discrepancies
| Model ID | System Price (input/output per 1K) | Current Price | Status |
|----------|-----------------------------------|---------------|--------|
```

---

### Task 3: Research IAM Suspension Mechanism

**Goal:** Verify the AmazonBedrockLimitedAccess policy still exists and the attach/detach suspension mechanism is still valid.

**Files to reference:**
- Read: `app/app/constructs/workflow_lambda_functions/iam_utilities.py` (suspension/restoration functions)
- Read: `app/app/constructs/workflow_orchestration.py` (Step Functions IAM permissions)

- [ ] **Step 1: Verify AmazonBedrockLimitedAccess managed policy**

Research:
- Does `arn:aws:iam::aws:policy/AmazonBedrockLimitedAccess` still exist?
- What permissions does it currently grant? Has the scope changed?
- Are there newer managed policies for Bedrock access (e.g., `AmazonBedrockFullAccess`, `AmazonBedrockReadOnly`)?
- Has the policy ARN format changed?

The system uses this policy in `iam_utilities.py`:
```python
managed_policy_arn = "arn:aws:iam::aws:policy/AmazonBedrockLimitedAccess"

# Suspension: iam_client.detach_user_policy(UserName=username, PolicyArn=managed_policy_arn)
# Restoration: iam_client.attach_user_policy(UserName=principal_id, PolicyArn=managed_policy_arn)
# Verification: iam_client.list_attached_user_policies(UserName=principal_id)
```

- [ ] **Step 2: Research Bedrock-native access control alternatives**

Check whether AWS has introduced better mechanisms for controlling Bedrock access:
- Bedrock resource policies or permissions boundaries
- Bedrock-native rate limiting or budget controls
- Service Control Policies (SCPs) specific to Bedrock
- Bedrock API key-level throttling or quotas
- Any AWS Cost Management integrations for Bedrock budgets

Document any alternatives that could replace or supplement the IAM policy detachment approach.

- [ ] **Step 3: Verify IAM API correctness for API key users**

Research:
- Are `AttachUserPolicy` / `DetachUserPolicy` still the correct API calls?
- Any changes to how Bedrock API key users (BedrockAPIKey- prefix) are managed in IAM?
- Has the Bedrock console changed how it creates API key users?

- [ ] **Step 4: Document findings for Stream 3**

Write findings in this format:
```markdown
## Stream 3: IAM Suspension Mechanism

### AmazonBedrockLimitedAccess Policy Status
- Exists: [yes/no]
- Permissions: [summary of current permissions]
- Changes since mid-2025: [list]

### Better Alternatives Available
- [alternative] — [description] — [recommendation]

### IAM API Correctness
- [any changes] — [impact] — [severity]
```

---

### Task 4: Research Cost Calculation Logic

**Goal:** Verify token pricing logic, image pricing, and new modality support.

**Files to reference:**
- Read: `app/app/constructs/shared/pricing_calculator.py` (calculate_cost, calculate_cost_with_cache)
- Read: `app/app/constructs/lambda_functions/usage_calculator.py` (_calculate_image_cost, _calculate_agent_flow_cost, _extract_converse_token_usage)

- [ ] **Step 1: Verify cache token pricing logic**

The system calculates cache token costs as:
```python
# Cache creation: charged at input token rate
cache_creation_cost = (cache_creation_tokens / 1000) * pricing['input_tokens_per_1000']
# Cache read: charged at 10% of input rate
cache_read_cost = (cache_read_tokens / 1000) * (pricing['input_tokens_per_1000'] * 0.1)
```

Research:
- What is the actual Bedrock cache token pricing? Is 10% for cache reads accurate?
- Does cache creation pricing differ from input token pricing?
- Are there model-specific cache pricing differences?
- Has Bedrock prompt caching pricing structure changed?

- [ ] **Step 2: Verify image generation pricing**

The system's `_calculate_image_cost()` uses per-image pricing:
```python
# Stability models: per-image rates (e.g., SDXL=$0.036, SD3=$0.035, Ultra=$0.06, Core=$0.04)
# Amazon models: Titan Image Gen v1/v2=$0.012, Nova Canvas=$0.04
```

Research:
- Are these per-image rates still current?
- Any new image generation models on Bedrock?
- Has pricing changed for any existing image models?
- Are there resolution-based pricing tiers?

- [ ] **Step 3: Verify Agent/Flow/KB pricing**

The system's `_calculate_agent_flow_cost()` uses:
```python
# Agents: token-based (same as model invocation)
# Flows: $0.035 per 1000 node transitions
# Knowledge Base Retrieve: per-query pricing
# Knowledge Base RetrieveAndGenerate: per-query + model pricing
```

Research:
- Is the Flow pricing of $0.035/1000 transitions still current?
- Has Agent pricing structure changed?
- Has Knowledge Base pricing changed?
- Any new pricing components for multi-agent collaboration?

- [ ] **Step 4: Check for new pricing modalities**

Research whether Bedrock now supports pricing dimensions the system doesn't handle:
- **Extended thinking / reasoning tokens** — Claude's thinking tokens may have separate pricing
- **Video generation** — Nova Reel or other video models
- **Audio / speech** — any TTS or audio models
- **Batch inference discounts** — has the batch pricing model changed?
- **Provisioned throughput** — any changes to committed use pricing?

- [ ] **Step 5: Document findings for Stream 4**

Write findings in this format:
```markdown
## Stream 4: Cost Calculation Logic

### Cache Token Pricing
- Current system assumption: [description]
- Actual pricing: [from docs]
- Discrepancy: [yes/no, details]

### Image Generation Pricing
| Model | System Price | Current Price | Status |
|-------|-------------|---------------|--------|

### Agent/Flow/KB Pricing
- [any changes]

### New Pricing Modalities Not Supported
- [modality] — [pricing structure] — [severity]
```

---

## Phase 2: Gap Analysis Consolidation (Task 5)

### Task 5: Consolidate Gap Analysis and Present to User

**Files:**
- Create: `docs/aws-api-gap-analysis.md`

- [ ] **Step 1: Merge findings from all 4 research streams**

Combine the outputs from Tasks 1-4 into a single document with this structure:

```markdown
# AWS API Gap Analysis — Bedrock Budgeteer

**Date:** 2026-04-03
**Scope:** Critical-path AWS API validation

## Executive Summary
[2-3 sentences: how many gaps found, severity distribution]

## Breaking Changes (must fix)
[List all BREAKING severity findings from all streams]

## Stale Data (should fix)
[List all STALE severity findings from all streams]

## Enhancement Opportunities (nice to have)
[List all ENHANCEMENT severity findings from all streams]

## Detailed Findings

### Stream 1: Bedrock API & CloudTrail Events
[Full findings from Task 1]

### Stream 2: AWS Pricing API for Bedrock
[Full findings from Task 2]

### Stream 3: IAM Suspension Mechanism
[Full findings from Task 3]

### Stream 4: Cost Calculation Logic
[Full findings from Task 4]
```

- [ ] **Step 2: Commit gap analysis**

```bash
cd /Users/danny.teller/tipalti/bedrock-budgeteer
git add docs/aws-api-gap-analysis.md
git commit -m "docs: add AWS API gap analysis from validation audit"
```

- [ ] **Step 3: Present findings to user for review**

Present the executive summary and the categorized findings. Ask the user:
1. Do they agree with the severity classifications?
2. Are there any findings they want to deprioritize or skip?
3. Are they ready to proceed to the fix phase?

**CHECKPOINT: Do NOT proceed to Phase 3 until the user explicitly approves.**

---

## Phase 3: Implementation (Tasks 6-8)

Tasks 6-8 are ordered by priority. Each task implements fixes for one severity level. The specific code changes depend on the gap analysis findings — the steps below show the **pattern** for each fix category with the exact files and code locations to modify.

### Task 6: Fix Breaking Changes

**Files (will be confirmed by gap analysis):**
- Modify: `app/app/constructs/event_ingestion.py` (EventBridge rule event patterns)
- Modify: `app/app/constructs/lambda_functions/usage_calculator.py` (event parsing)
- Modify: `app/tests/unit/test_integration.py` (EventBridge rule assertions)
- Modify: `app/tests/unit/test_core_processing.py` (usage calculator tests)

- [ ] **Step 1: Write failing tests for new Bedrock event names**

For each new Bedrock API operation found in Task 1, add a test that asserts the EventBridge rule includes it. Example pattern (adjust event names based on actual findings):

In `app/tests/unit/test_integration.py`, add to `test_eventbridge_rules_created()`:
```python
# Verify the Bedrock usage rule includes [NEW_EVENT_NAME]
self.template.has_resource("AWS::Events::Rule", {
    "Properties": {
        "Name": "bedrock-budgeteer-production-bedrock-usage",
        "EventPattern": {
            "detail": {
                "eventName": assertions.Match.array_with([
                    "[NEW_EVENT_NAME]"
                ])
            }
        }
    }
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/danny.teller/tipalti/bedrock-budgeteer/app
python -m pytest tests/unit/test_integration.py::TestIntegration::test_eventbridge_rules_created -v
```

Expected: FAIL — new event names not yet in the EventBridge rule.

- [ ] **Step 3: Add new event names to EventBridge rules**

In `app/app/constructs/event_ingestion.py`, update the BedrockUsageRule event pattern to include new event names. The rule is defined around line 160:

```python
# Add new events to the eventName list in the EventBridge rule
events.Rule(
    self, "BedrockUsageRule",
    rule_name=f"bedrock-budgeteer-{environment_name}-bedrock-usage",
    event_pattern=events.EventPattern(
        source=["aws.bedrock"],
        detail_type=["AWS API Call via CloudTrail"],
        detail={
            "eventSource": ["bedrock.amazonaws.com"],
            "eventName": [
                "InvokeModel",
                "InvokeModelWithResponseStream",
                "Converse",
                "ConverseStream",
                "GetFoundationModel",
                "ListFoundationModels",
                # ADD NEW EVENTS HERE based on gap analysis
            ]
        }
    ),
    targets=[targets.LambdaFunction(usage_calculator_lambda)]
)
```

- [ ] **Step 4: Update usage_calculator to handle new event schemas**

If CloudTrail event schema changes were found in Task 1, update the event parsing in `usage_calculator.py`. Key locations:
- `process_bedrock_log()` — the main routing function that checks `eventName`
- `_resolve_model_id_from_arn()` — if model ID format changed
- `_extract_converse_token_usage()` — if Converse response schema changed

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /Users/danny.teller/tipalti/bedrock-budgeteer/app
python -m pytest tests/unit/test_integration.py -v
python -m pytest tests/unit/test_core_processing.py -v
```

Expected: ALL PASS

- [ ] **Step 6: Commit breaking change fixes**

```bash
cd /Users/danny.teller/tipalti/bedrock-budgeteer
git add app/app/constructs/event_ingestion.py app/app/constructs/lambda_functions/usage_calculator.py
git add app/tests/unit/test_integration.py app/tests/unit/test_core_processing.py
git commit -m "fix: update Bedrock CloudTrail event patterns and parsing for current API"
```

---

### Task 7: Fix Stale Data

**Files:**
- Modify: `app/app/constructs/shared/pricing_calculator.py` (fallback prices, cache pricing)
- Modify: `app/tests/unit/test_core_processing.py` (pricing tests)

- [ ] **Step 1: Write failing tests for updated pricing**

For each model with changed pricing found in Task 2, add/update test assertions. In `app/tests/unit/test_core_processing.py`:

```python
def test_fallback_pricing_accuracy(self):
    """Verify fallback prices match current AWS pricing"""
    from app.constructs.shared.pricing_calculator import BedrockPricingCalculator

    # Test each model's fallback pricing matches current rates
    # (specific models and rates from gap analysis)
    pricing = BedrockPricingCalculator._get_fallback_pricing('anthropic.claude-3-5-sonnet-20241022-v2:0')
    self.assertAlmostEqual(pricing['input_tokens_per_1000'], EXPECTED_INPUT_RATE, places=6)
    self.assertAlmostEqual(pricing['output_tokens_per_1000'], EXPECTED_OUTPUT_RATE, places=6)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/danny.teller/tipalti/bedrock-budgeteer/app
python -m pytest tests/unit/test_core_processing.py -k "pricing" -v
```

Expected: FAIL for models with changed prices.

- [ ] **Step 3: Update fallback pricing table**

In `app/app/constructs/shared/pricing_calculator.py`, update the `model_pricing` dict in `_get_fallback_pricing()`:
- Fix prices for models that changed
- Add entries for new models (from gap analysis)
- Remove entries for deprecated models

- [ ] **Step 4: Update cache token pricing if needed**

If Task 4 found that the 10% cache read assumption is wrong, update `calculate_cost_with_cache()`:

```python
# In pricing_calculator.py, update the cache read discount factor
cache_read_cost = (cache_read_tokens / 1000) * (pricing['input_tokens_per_1000'] * CORRECT_DISCOUNT_FACTOR)
```

- [ ] **Step 5: Add new pricing dimensions if needed**

If Task 2/4 found new pricing dimensions (reasoning tokens, video, audio), add support:
- Add new fields to the pricing dict structure
- Update `calculate_cost()` and `calculate_cost_with_cache()` to account for them
- Update the usage_calculator to extract new token types from events

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /Users/danny.teller/tipalti/bedrock-budgeteer/app
python -m pytest tests/unit/test_core_processing.py -v
```

Expected: ALL PASS

- [ ] **Step 7: Commit stale data fixes**

```bash
cd /Users/danny.teller/tipalti/bedrock-budgeteer
git add app/app/constructs/shared/pricing_calculator.py
git add app/tests/unit/test_core_processing.py
git commit -m "fix: update Bedrock model pricing fallbacks and cost calculation logic"
```

---

### Task 8: Fix Mechanism Improvements (if applicable)

**Files (conditional on gap analysis findings):**
- Modify: `app/app/constructs/workflow_lambda_functions/iam_utilities.py`
- Modify: `app/app/constructs/lambda_functions/usage_calculator.py`
- Modify: `app/tests/unit/test_budget_blocking_workflow.py`

- [ ] **Step 1: Evaluate IAM mechanism findings**

Review Stream 3 findings. If `AmazonBedrockLimitedAccess` still exists and the attach/detach mechanism is still valid, this step is a no-op — skip to Step 4.

If the policy was deprecated or a better mechanism exists:

- [ ] **Step 2: Write failing tests for updated suspension mechanism**

```python
def test_suspension_uses_updated_mechanism(self):
    """Test that suspension uses the current recommended approach"""
    # Specific test based on gap analysis findings
    pass
```

- [ ] **Step 3: Update iam_utilities.py with new mechanism**

Replace the hardcoded `AmazonBedrockLimitedAccess` references if needed. The policy ARN appears in:
- `apply_full_suspension()` — line ~100
- `restore_bedrock_access()` — line ~135
- `check_iam_state()` — line ~247

- [ ] **Step 4: Add support for new Bedrock invocation patterns**

If Task 1 found new Bedrock API operations that should be budget-tracked, add handling in `usage_calculator.py`:
- Add routing in `process_bedrock_log()` for new event names
- Add cost calculation logic for new operation types
- Add metrics publishing for new event types

- [ ] **Step 5: Run full test suite**

```bash
cd /Users/danny.teller/tipalti/bedrock-budgeteer/app
python -m pytest tests/unit/ -v
```

Expected: ALL PASS

- [ ] **Step 6: Commit mechanism improvements**

```bash
cd /Users/danny.teller/tipalti/bedrock-budgeteer
git add -A
git commit -m "feat: update suspension mechanism and add support for new Bedrock operations"
```

---

## Phase 4: Validation (Task 9)

### Task 9: Final Validation and Documentation

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/danny.teller/tipalti/bedrock-budgeteer/app
python -m pytest tests/unit/ -v
```

Expected: ALL PASS, no regressions.

- [ ] **Step 2: Verify CDK synth**

```bash
cd /Users/danny.teller/tipalti/bedrock-budgeteer/app
cdk synth --quiet
```

Expected: Template synthesized successfully with no errors.

- [ ] **Step 3: Update CHANGELOG.md**

Add entry to CHANGELOG.md documenting what was updated and why:

```markdown
## [Unreleased]

### Changed
- Updated EventBridge rules with current Bedrock API event names
- Updated fallback pricing table with current Bedrock model prices
- [Other changes based on actual findings]

### Added
- Support for [new models/operations based on findings]
- [Other additions]

### Fixed
- [Any corrections found during audit]
```

- [ ] **Step 4: Commit changelog and final verification**

```bash
cd /Users/danny.teller/tipalti/bedrock-budgeteer
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for AWS API validation audit"
```

- [ ] **Step 5: Summary report**

Present to user:
- Total gaps found vs fixed
- Any gaps deferred and why
- Remaining risks or items to watch
