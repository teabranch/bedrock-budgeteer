"""
Key Provisioning Construct for Bedrock Budgeteer

Provisions tagged IAM users for Bedrock API keys. Each user follows the
BedrockAPIKey-{team}-{purpose} naming convention and is tagged with
budget tier, team, and purpose metadata for cost tracking and budget enforcement.
"""
from typing import Optional

from aws_cdk import (
    Tags,
    aws_iam as iam,
    aws_kms as kms,
)
from constructs import Construct

VALID_BUDGET_TIERS = ("low", "medium", "high")


class KeyProvisioningConstruct(Construct):
    """Construct that provisions a tagged IAM user for Bedrock API key access."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        team: str,
        purpose: str,
        budget_tier: str,
        environment_name: str,
        kms_key: Optional[kms.Key] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        if budget_tier not in VALID_BUDGET_TIERS:
            raise ValueError(
                f"Invalid budget_tier '{budget_tier}'. "
                f"Must be one of: {', '.join(VALID_BUDGET_TIERS)}"
            )

        self.environment_name = environment_name
        self.kms_key = kms_key

        # Create the IAM user with the standard naming convention
        self._user = iam.User(
            self,
            "BedrockApiKeyUser",
            user_name=f"BedrockAPIKey-{team}-{purpose}",
        )

        # Attach the Bedrock managed policy
        self._user.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "AmazonBedrockLimitedAccess"
            )
        )

        # Apply all required tags
        tags = {
            "BedrockBudgeteer:Team": team,
            "BedrockBudgeteer:Purpose": purpose,
            "BedrockBudgeteer:BudgetTier": budget_tier,
            "BedrockBudgeteer:Provisioned": "cdk",
            "BedrockBudgeteer:ManagedBy": "bedrock-budgeteer",
            "CostAllocation:Team": team,
            "CostAllocation:Purpose": purpose,
        }
        for key, value in tags.items():
            Tags.of(self._user).add(key, value)

    @property
    def user_name(self) -> str:
        """The name of the provisioned IAM user."""
        return self._user.user_name

    @property
    def user_arn(self) -> str:
        """The ARN of the provisioned IAM user."""
        return self._user.user_arn
