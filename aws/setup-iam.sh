#!/bin/bash
# -----------------------------------------------------------------------------
# GANTRY IAM SETUP SCRIPT
# -----------------------------------------------------------------------------
# This script creates an IAM user with the minimum permissions required
# to use Amazon Bedrock with the Gantry system.
#
# Prerequisites:
#   - AWS CLI installed and configured with admin credentials
#   - jq installed (brew install jq)
#
# Usage:
#   chmod +x aws/setup-iam.sh
#   ./aws/setup-iam.sh
# -----------------------------------------------------------------------------

set -e

# Configuration
IAM_USER_NAME="gantry-bedrock-user"
POLICY_NAME="GantryBedrockAccess"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

echo "=========================================="
echo "  GANTRY IAM SETUP"
echo "=========================================="
echo ""

# Check prerequisites
if ! command -v aws &> /dev/null; then
    echo "ERROR: AWS CLI not installed. Install it first:"
    echo "  brew install awscli"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo "ERROR: jq not installed. Install it first:"
    echo "  brew install jq"
    exit 1
fi

# Verify AWS credentials are working
echo "[1/5] Verifying AWS credentials..."
if ! aws sts get-caller-identity &> /dev/null; then
    echo "ERROR: AWS credentials not configured or expired."
    echo "Please configure AWS CLI with admin credentials first:"
    echo "  aws configure"
    exit 1
fi
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "       Account: $ACCOUNT_ID"

# Create the IAM policy
echo "[2/5] Creating IAM policy: $POLICY_NAME..."
POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy/${POLICY_NAME}"

# Check if policy already exists
if aws iam get-policy --policy-arn "$POLICY_ARN" &> /dev/null; then
    echo "       Policy already exists, skipping creation."
else
    aws iam create-policy \
        --policy-name "$POLICY_NAME" \
        --policy-document file://aws/bedrock-policy.json \
        --description "Minimum permissions for Gantry to use Amazon Bedrock" \
        > /dev/null
    echo "       Policy created: $POLICY_ARN"
fi

# Create the IAM user
echo "[3/5] Creating IAM user: $IAM_USER_NAME..."
if aws iam get-user --user-name "$IAM_USER_NAME" &> /dev/null; then
    echo "       User already exists, skipping creation."
else
    aws iam create-user --user-name "$IAM_USER_NAME" > /dev/null
    echo "       User created."
fi

# Attach policy to user
echo "[4/5] Attaching policy to user..."
aws iam attach-user-policy \
    --user-name "$IAM_USER_NAME" \
    --policy-arn "$POLICY_ARN" 2>/dev/null || true
echo "       Policy attached."

# Create access keys
echo "[5/5] Creating access keys..."
echo ""

# Check if user already has access keys
EXISTING_KEYS=$(aws iam list-access-keys --user-name "$IAM_USER_NAME" --query 'AccessKeyMetadata[*].AccessKeyId' --output text)
if [ -n "$EXISTING_KEYS" ]; then
    echo "WARNING: User already has access keys: $EXISTING_KEYS"
    echo "Do you want to create new keys? (existing keys will remain) [y/N]"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        echo "Skipping key creation."
        echo ""
        echo "=========================================="
        echo "  SETUP COMPLETE (no new keys created)"
        echo "=========================================="
        exit 0
    fi
fi

# Create new access keys
KEYS=$(aws iam create-access-key --user-name "$IAM_USER_NAME")
ACCESS_KEY_ID=$(echo "$KEYS" | jq -r '.AccessKey.AccessKeyId')
SECRET_ACCESS_KEY=$(echo "$KEYS" | jq -r '.AccessKey.SecretAccessKey')

echo "=========================================="
echo "  SETUP COMPLETE"
echo "=========================================="
echo ""
echo "Your new AWS credentials:"
echo ""
echo "  AWS_ACCESS_KEY_ID=$ACCESS_KEY_ID"
echo "  AWS_SECRET_ACCESS_KEY=$SECRET_ACCESS_KEY"
echo "  AWS_DEFAULT_REGION=$REGION"
echo ""
echo "=========================================="
echo ""
echo "OPTION 1: Add to ~/.aws/credentials"
echo ""
echo "  Add this to your ~/.aws/credentials file:"
echo ""
echo "  [gantry]"
echo "  aws_access_key_id = $ACCESS_KEY_ID"
echo "  aws_secret_access_key = $SECRET_ACCESS_KEY"
echo ""
echo "  Then run Gantry with:"
echo "    export AWS_PROFILE=gantry"
echo "    python src/main.py"
echo ""
echo "=========================================="
echo ""
echo "OPTION 2: Create a .env file"
echo ""
echo "  echo 'AWS_ACCESS_KEY_ID=$ACCESS_KEY_ID' > .env"
echo "  echo 'AWS_SECRET_ACCESS_KEY=$SECRET_ACCESS_KEY' >> .env"
echo "  echo 'AWS_DEFAULT_REGION=$REGION' >> .env"
echo ""
echo "=========================================="
echo ""
echo "IMPORTANT: Store these credentials securely!"
echo "           They will NOT be shown again."
echo ""
