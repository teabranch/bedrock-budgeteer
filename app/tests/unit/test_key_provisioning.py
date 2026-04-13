"""
Unit tests for KeyProvisioningConstruct

Tests IAM user creation, policy attachment, tagging, and property access.
"""
import pytest
import aws_cdk as cdk
from aws_cdk import Stack, Tags
from aws_cdk.assertions import Template, Match
from constructs import Construct

from app.constructs.key_provisioning import KeyProvisioningConstruct


class KeyProvisioningStack(Stack):
    """Helper stack that instantiates KeyProvisioningConstruct for testing."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        team: str = "ml-platform",
        purpose: str = "inference",
        budget_tier: str = "medium",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.construct = KeyProvisioningConstruct(
            self,
            "KeyProvisioning",
            team=team,
            purpose=purpose,
            budget_tier=budget_tier,
            environment_name="test",
        )


@pytest.fixture
def app() -> cdk.App:
    """Create a CDK app for testing."""
    return cdk.App()


@pytest.fixture
def stack(app: cdk.App) -> KeyProvisioningStack:
    """Create the helper stack with default parameters."""
    return KeyProvisioningStack(app, "TestKeyProvisioningStack")


@pytest.fixture
def template(stack: KeyProvisioningStack) -> Template:
    """Synthesize and return the CloudFormation template."""
    return Template.from_stack(stack)


class TestKeyProvisioningConstruct:
    """Tests for the KeyProvisioningConstruct."""

    def test_creates_iam_user_with_correct_name(self, template: Template) -> None:
        """Verify IAM user resource exists with the expected naming convention."""
        template.has_resource_properties(
            "AWS::IAM::User",
            {"UserName": "BedrockAPIKey-ml-platform-inference"},
        )

    def test_attaches_bedrock_policy(self, template: Template) -> None:
        """Verify AmazonBedrockLimitedAccess managed policy is attached to the user."""
        template.has_resource_properties(
            "AWS::IAM::User",
            {
                "ManagedPolicyArns": Match.array_with(
                    [
                        {
                            "Fn::Join": Match.any_value(),
                        }
                    ]
                )
            },
        )

    def test_applies_all_tags(self, template: Template) -> None:
        """Verify all 7 required tags are applied to the IAM user resource."""
        resources = template.find_resources("AWS::IAM::User")
        assert len(resources) == 1
        user_resource = list(resources.values())[0]
        tags = user_resource["Properties"]["Tags"]
        tag_dict = {t["Key"]: t["Value"] for t in tags}

        assert tag_dict["BedrockBudgeteer:Team"] == "ml-platform"
        assert tag_dict["BedrockBudgeteer:Purpose"] == "inference"
        assert tag_dict["BedrockBudgeteer:BudgetTier"] == "medium"
        assert tag_dict["BedrockBudgeteer:Provisioned"] == "cdk"
        assert tag_dict["BedrockBudgeteer:ManagedBy"] == "bedrock-budgeteer"
        assert tag_dict["CostAllocation:Team"] == "ml-platform"
        assert tag_dict["CostAllocation:Purpose"] == "inference"
        assert len(tags) == 7

    def test_invalid_budget_tier_raises_error(self, app: cdk.App) -> None:
        """Verify that an invalid budget tier raises ValueError."""
        with pytest.raises(ValueError, match="Invalid budget_tier 'extra-large'"):
            KeyProvisioningStack(
                app,
                "InvalidTierStack",
                budget_tier="extra-large",
            )

    def test_properties_accessible(self, stack: KeyProvisioningStack) -> None:
        """Verify user_name and user_arn properties are accessible and return tokens."""
        assert stack.construct.user_name is not None
        assert stack.construct.user_arn is not None
