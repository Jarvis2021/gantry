#!/bin/bash
# -----------------------------------------------------------------------------
# GANTRY IAM ROLE SETUP SCRIPT
# -----------------------------------------------------------------------------
# Creates an IAM Role (not user) for Bedrock access.
# More secure than access keys - uses temporary credentials via role assumption.
#
# Prerequisites:
#   - AWS CLI installed and configured with admin credentials
#   - jq installed (brew install jq)
#
# Usage:
#   chmod +x aws/setup-iam-role.sh
#   ./aws/setup-iam-role.sh
# -----------------------------------------------------------------------------

set -e

# Configuration
ROLE_NAME="GantryBedrockRole"
POLICY_NAME="GantryBedrockAccess"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

echo "=========================================="
echo "  GANTRY IAM ROLE SETUP"
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
    echo "Please login first:"
    echo "  aws sso login --profile YOUR_PROFILE"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
CALLER_ARN=$(aws sts get-caller-identity --query Arn --output text)
echo "       Account: $ACCOUNT_ID"
echo "       Caller: $CALLER_ARN"

# Create the IAM policy
echo "[2/5] Creating IAM policy: $POLICY_NAME..."
POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy/${POLICY_NAME}"

if aws iam get-policy --policy-arn "$POLICY_ARN" &> /dev/null; then
    echo "       Policy already exists."
else
    aws iam create-policy \
        --policy-name "$POLICY_NAME" \
        --policy-document file://aws/bedrock-policy.json \
        --description "Minimum permissions for Gantry to use Amazon Bedrock" \
        > /dev/null
    echo "       Policy created: $POLICY_ARN"
fi

# Create trust policy (allow current account to assume the role)
echo "[3/5] Creating trust policy..."
TRUST_POLICY=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::${ACCOUNT_ID}:root"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
EOF
)

# Create the IAM role
echo "[4/5] Creating IAM role: $ROLE_NAME..."
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

if aws iam get-role --role-name "$ROLE_NAME" &> /dev/null; then
    echo "       Role already exists."
else
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document "$TRUST_POLICY" \
        --description "IAM Role for Gantry Bedrock access" \
        > /dev/null
    echo "       Role created."
fi

# Attach policy to role
echo "[5/5] Attaching policy to role..."
aws iam attach-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-arn "$POLICY_ARN" 2>/dev/null || true
echo "       Policy attached."

echo ""
echo "=========================================="
echo "  SETUP COMPLETE"
echo "=========================================="
echo ""
echo "Role ARN:"
echo "  $ROLE_ARN"
echo ""
echo "=========================================="
echo ""
echo "CONFIGURATION OPTIONS:"
echo ""
echo "Option 1: Add to ~/.aws/config (Recommended)"
echo ""
echo "  Add this to your ~/.aws/config file:"
echo ""
echo "  [profile gantry]"
echo "  role_arn = $ROLE_ARN"
echo "  source_profile = YOUR_AWS_PROFILE"
echo "  region = $REGION"
echo ""
echo "  Then run Gantry with:"
echo "    export AWS_PROFILE=gantry"
echo "    python src/main.py"
echo ""
echo "=========================================="
echo ""
echo "Option 2: Use Role ARN directly in .env"
echo ""
echo "  echo 'AWS_ROLE_ARN=$ROLE_ARN' > .env"
echo "  echo 'AWS_DEFAULT_REGION=$REGION' >> .env"
echo ""
echo "=========================================="
echo ""
