#!/usr/bin/env python3
"""CLI to provision and manage Bedrock API keys directly via AWS APIs.

Usage:
    ./manage_keys.py add --team platform --purpose chatbot-prod --budget-tier medium
    ./manage_keys.py remove --team platform --purpose chatbot-prod
    ./manage_keys.py list

Creates an IAM user, attaches AmazonBedrockLimitedAccess policy, and generates
a Bedrock API key (service-specific credential). No CDK deploy needed.
The existing CloudTrail → EventBridge → user_setup pipeline will automatically
detect the new user and register its budget based on tags.

Note: Service-specific credentials have no built-in expiry via the IAM API.
Implement rotation externally by scheduling deletion based on CreateDate.
"""
import argparse
import re
import sys

import boto3
from botocore.exceptions import ClientError

VALID_TIERS = ("low", "medium", "high")
TIER_BUDGETS = {"low": "$1", "medium": "$5", "high": "$25"}
BEDROCK_POLICY_ARN = "arn:aws:iam::aws:policy/AmazonBedrockLimitedAccess"
BEDROCK_SERVICE_NAME = "bedrock.amazonaws.com"
USER_PREFIX = "BedrockAPIKey-"
_SAFE_LABEL_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def _validate_label(value: str) -> str:
    """Validate team/purpose labels contain only IAM-safe characters."""
    if not _SAFE_LABEL_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"'{value}' contains invalid characters. Use only a-z, A-Z, 0-9, '.', '_', '-'."
        )
    return value


def get_iam_client():
    return boto3.client("iam")


def build_user_name(team: str, purpose: str) -> str:
    return f"{USER_PREFIX}{team}-{purpose}"


def build_tags(team: str, purpose: str, budget_tier: str) -> list[dict[str, str]]:
    return [
        {"Key": "BedrockBudgeteer:Team", "Value": team},
        {"Key": "BedrockBudgeteer:Purpose", "Value": purpose},
        {"Key": "BedrockBudgeteer:BudgetTier", "Value": budget_tier},
        {"Key": "BedrockBudgeteer:Provisioned", "Value": "script"},
        {"Key": "BedrockBudgeteer:ManagedBy", "Value": "bedrock-budgeteer"},
        {"Key": "CostAllocation:Team", "Value": team},
        {"Key": "CostAllocation:Purpose", "Value": purpose},
    ]


def add_key(args: argparse.Namespace) -> None:
    iam = get_iam_client()
    user_name = build_user_name(args.team, args.purpose)
    tags = build_tags(args.team, args.purpose, args.budget_tier)

    try:
        iam.create_user(UserName=user_name, Tags=tags)
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityAlreadyExists":
            print(f"Error: IAM user '{user_name}' already exists.", file=sys.stderr)
            print("Use 'list' to see existing keys or 'remove' first.", file=sys.stderr)
            sys.exit(1)
        raise

    # Attach policy and create API key — rollback user on failure
    try:
        iam.attach_user_policy(UserName=user_name, PolicyArn=BEDROCK_POLICY_ARN)

        cred_response = iam.create_service_specific_credential(
            UserName=user_name,
            ServiceName=BEDROCK_SERVICE_NAME,
        )
        cred = cred_response["ServiceSpecificCredential"]
    except Exception:
        # Rollback: clean up the orphaned user
        try:
            iam.detach_user_policy(UserName=user_name, PolicyArn=BEDROCK_POLICY_ARN)
        except ClientError:
            pass
        try:
            iam.delete_user(UserName=user_name)
        except ClientError:
            pass
        print(f"Error: failed to finish provisioning '{user_name}'. User has been rolled back.", file=sys.stderr)
        raise

    print(f"Created: {user_name}")
    print(f"  Budget tier: {args.budget_tier} ({TIER_BUDGETS[args.budget_tier]})")
    print(f"  Policy: AmazonBedrockLimitedAccess")
    print(f"  Tags: team={args.team}, purpose={args.purpose}")
    print()
    print("Bedrock API Key:")
    print(f"  API Key Value:   {cred['ServiceApiKeyValue']}")
    print(f"  Credential ID:   {cred['ServiceSpecificCredentialId']}")
    print()
    print("IMPORTANT: Save the API Key Value now — it cannot be retrieved again.")
    print()
    print("The user_setup Lambda will automatically register this key's budget")
    print("when CloudTrail delivers the CreateUser event (typically within minutes).")


def remove_key(args: argparse.Namespace) -> None:
    iam = get_iam_client()
    user_name = build_user_name(args.team, args.purpose)

    try:
        iam.get_user(UserName=user_name)
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchEntity":
            print(f"Error: IAM user '{user_name}' does not exist.", file=sys.stderr)
            sys.exit(1)
        raise

    # Detach managed policies (paginated)
    paginator = iam.get_paginator("list_attached_user_policies")
    for page in paginator.paginate(UserName=user_name):
        for policy in page.get("AttachedPolicies", []):
            iam.detach_user_policy(UserName=user_name, PolicyArn=policy["PolicyArn"])

    # Delete inline policies (paginated)
    paginator = iam.get_paginator("list_user_policies")
    for page in paginator.paginate(UserName=user_name):
        for policy_name in page.get("PolicyNames", []):
            iam.delete_user_policy(UserName=user_name, PolicyName=policy_name)

    # Delete access keys (paginated)
    paginator = iam.get_paginator("list_access_keys")
    for page in paginator.paginate(UserName=user_name):
        for key in page.get("AccessKeyMetadata", []):
            iam.delete_access_key(UserName=user_name, AccessKeyId=key["AccessKeyId"])

    # Delete service-specific credentials (no paginator — 100-item API hard limit)
    creds = iam.list_service_specific_credentials(UserName=user_name)
    for cred in creds.get("ServiceSpecificCredentials", []):
        iam.delete_service_specific_credential(
            UserName=user_name,
            ServiceSpecificCredentialId=cred["ServiceSpecificCredentialId"],
        )

    # Delete login profile if it exists (console password)
    try:
        iam.delete_login_profile(UserName=user_name)
    except ClientError as e:
        if e.response["Error"]["Code"] != "NoSuchEntity":
            raise

    # Delete MFA devices
    mfa_devices = iam.list_mfa_devices(UserName=user_name)
    for device in mfa_devices.get("MFADevices", []):
        iam.deactivate_mfa_device(UserName=user_name, SerialNumber=device["SerialNumber"])
        iam.delete_virtual_mfa_device(SerialNumber=device["SerialNumber"])

    iam.delete_user(UserName=user_name)
    print(f"Removed: {user_name}")
    print("Note: Budget records in DynamoDB will remain for audit purposes.")


def list_keys(_args: argparse.Namespace) -> None:
    iam = get_iam_client()

    paginator = iam.get_paginator("list_users")
    users = []
    for page in paginator.paginate():
        for user in page["Users"]:
            if user["UserName"].startswith(USER_PREFIX):
                users.append(user)

    if not users:
        print("No BedrockAPIKey-* IAM users found.")
        return

    print(f"{'IAM User Name':<45} {'Team':<15} {'Purpose':<20} {'Tier':<8} {'Source':<8}")
    print("-" * 96)

    for user in sorted(users, key=lambda u: u["UserName"]):
        tags_resp = iam.list_user_tags(UserName=user["UserName"])
        tags = {t["Key"]: t["Value"] for t in tags_resp.get("Tags", [])}

        team = tags.get("BedrockBudgeteer:Team", "-")
        purpose = tags.get("BedrockBudgeteer:Purpose", "-")
        tier = tags.get("BedrockBudgeteer:BudgetTier", "-")
        source = tags.get("BedrockBudgeteer:Provisioned", "unknown")

        print(f"{user['UserName']:<45} {team:<15} {purpose:<20} {tier:<8} {source:<8}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage Bedrock API key IAM users (creates/removes directly in AWS)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Keys are provisioned immediately — no CDK deploy needed.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Create a new Bedrock API key user")
    add_parser.add_argument("--team", required=True, type=_validate_label,
                            help="Team name (e.g., platform, ml-ops)")
    add_parser.add_argument("--purpose", required=True, type=_validate_label,
                            help="Purpose/use case (e.g., chatbot-prod)")
    add_parser.add_argument("--budget-tier", default="low", choices=VALID_TIERS,
                            help="Budget tier: low=$1, medium=$5, high=$25 (default: low)")
    add_parser.set_defaults(func=add_key)

    rm_parser = subparsers.add_parser("remove", help="Remove a Bedrock API key user")
    rm_parser.add_argument("--team", required=True, type=_validate_label, help="Team name")
    rm_parser.add_argument("--purpose", required=True, type=_validate_label,
                           help="Purpose/use case")
    rm_parser.set_defaults(func=remove_key)

    subparsers.add_parser("list", help="List all BedrockAPIKey-* IAM users").set_defaults(func=list_keys)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
