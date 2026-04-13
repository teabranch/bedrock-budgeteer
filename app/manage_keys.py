#!/usr/bin/env python3
"""CLI to provision and manage Bedrock API key IAM users directly via AWS APIs.

Usage:
    ./manage_keys.py add --team platform --purpose chatbot-prod --budget-tier medium
    ./manage_keys.py remove --team platform --purpose chatbot-prod
    ./manage_keys.py list

Keys are created immediately in AWS IAM — no CDK deploy needed.
The existing CloudTrail → EventBridge → user_setup pipeline will automatically
detect the new user and register its budget based on tags.
"""
import argparse
import sys
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

VALID_TIERS = ("low", "medium", "high")
TIER_BUDGETS = {"low": "$1", "medium": "$5", "high": "$25"}
BEDROCK_POLICY_ARN = "arn:aws:iam::aws:policy/AmazonBedrockLimitedAccess"
USER_PREFIX = "BedrockAPIKey-"


def get_iam_client() -> "boto3.client":
    return boto3.client("iam")


def build_user_name(team: str, purpose: str) -> str:
    return f"{USER_PREFIX}{team}-{purpose}"


def build_tags(team: str, purpose: str, budget_tier: str) -> List[Dict[str, str]]:
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

    iam.attach_user_policy(UserName=user_name, PolicyArn=BEDROCK_POLICY_ARN)

    print(f"Created: {user_name}")
    print(f"  Budget tier: {args.budget_tier} ({TIER_BUDGETS[args.budget_tier]})")
    print(f"  Policy: AmazonBedrockLimitedAccess")
    print(f"  Tags: team={args.team}, purpose={args.purpose}")
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

    # Detach managed policies
    attached = iam.list_attached_user_policies(UserName=user_name)
    for policy in attached.get("AttachedPolicies", []):
        iam.detach_user_policy(UserName=user_name, PolicyArn=policy["PolicyArn"])

    # Delete inline policies
    inline = iam.list_user_policies(UserName=user_name)
    for policy_name in inline.get("PolicyNames", []):
        iam.delete_user_policy(UserName=user_name, PolicyName=policy_name)

    # Delete access keys
    keys = iam.list_access_keys(UserName=user_name)
    for key in keys.get("AccessKeyMetadata", []):
        iam.delete_access_key(UserName=user_name, AccessKeyId=key["AccessKeyId"])

    # Delete service-specific credentials
    creds = iam.list_service_specific_credentials(UserName=user_name)
    for cred in creds.get("ServiceSpecificCredentials", []):
        iam.delete_service_specific_credential(
            UserName=user_name,
            ServiceSpecificCredentialId=cred["ServiceSpecificCredentialId"],
        )

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
    add_parser.add_argument("--team", required=True, help="Team name (e.g., platform, ml-ops)")
    add_parser.add_argument("--purpose", required=True, help="Purpose/use case (e.g., chatbot-prod)")
    add_parser.add_argument("--budget-tier", default="low", choices=VALID_TIERS,
                            help="Budget tier: low=$1, medium=$5, high=$25 (default: low)")
    add_parser.set_defaults(func=add_key)

    rm_parser = subparsers.add_parser("remove", help="Remove a Bedrock API key user")
    rm_parser.add_argument("--team", required=True, help="Team name")
    rm_parser.add_argument("--purpose", required=True, help="Purpose/use case")
    rm_parser.set_defaults(func=remove_key)

    list_parser = subparsers.add_parser("list", help="List all BedrockAPIKey-* IAM users")
    list_parser.set_defaults(func=list_keys)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
