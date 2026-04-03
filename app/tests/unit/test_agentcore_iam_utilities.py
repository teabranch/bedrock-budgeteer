"""Tests for AgentCore IAM utilities Lambda function code"""
import unittest


class TestAgentCoreIamUtilitiesContent(unittest.TestCase):
    """Validate agentcore_iam_utilities Lambda code"""

    def setUp(self):
        from app.constructs.workflow_lambda_functions.agentcore_iam_utilities import (
            get_agentcore_iam_utilities_function_code
        )
        self.code = get_agentcore_iam_utilities_function_code()

    def test_contains_lambda_handler(self):
        self.assertIn('def lambda_handler(event, context):', self.code)

    def test_handles_apply_restriction(self):
        self.assertIn("action == 'apply_restriction'", self.code)

    def test_handles_restore_access(self):
        self.assertIn("action == 'restore_access'", self.code)

    def test_handles_validate_restrictions(self):
        self.assertIn("action == 'validate_restrictions'", self.code)

    def test_snapshots_managed_policies(self):
        self.assertIn('list_attached_role_policies', self.code)

    def test_snapshots_inline_policies(self):
        self.assertIn('list_role_policies', self.code)
        self.assertIn('get_role_policy', self.code)

    def test_detaches_managed_policies(self):
        self.assertIn('detach_role_policy', self.code)

    def test_deletes_inline_policies(self):
        self.assertIn('delete_role_policy', self.code)

    def test_attaches_deny_all(self):
        self.assertIn('BedrockBudgeteerDenyAll', self.code)

    def test_restores_managed_policies(self):
        self.assertIn('attach_role_policy', self.code)

    def test_restores_inline_policies(self):
        self.assertIn('put_role_policy', self.code)

    def test_tags_role(self):
        self.assertIn('tag_role', self.code)
        self.assertIn('BedrockBudgeteerRestricted', self.code)

    def test_untags_role(self):
        self.assertIn('untag_role', self.code)

    def test_stores_snapshot_in_dynamodb(self):
        self.assertIn('policy_snapshot', self.code)

    def test_supports_agentcore_account_type(self):
        self.assertIn('agentcore_runtime', self.code)


if __name__ == '__main__':
    unittest.main()
