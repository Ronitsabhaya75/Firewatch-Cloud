# 🚀 Firewatch Deployment Guide

Complete step-by-step guide to deploy Firewatch to AWS.

---

## ⚡ Quick Start

```bash
# 1. Setup environment
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate.bat

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure AWS credentials (if not already done)
aws configure

# 4. Bootstrap CDK (first time only)
cdk bootstrap

# 5. Deploy
cdk deploy

# 6. Update API keys (see below)
```

---

## 📋 Prerequisites Checklist

### Required

- [ ] **AWS Account** with administrator access
- [ ] **AWS CLI** installed and configured
  ```bash
  aws --version  # Should be v2.x or higher
  aws sts get-caller-identity  # Verify credentials work
  ```
- [ ] **Node.js 18+** (for AWS CDK)
  ```bash
  node --version  # Should be v18.x or higher
  ```
- [ ] **AWS CDK** installed globally
  ```bash
  npm install -g aws-cdk
  cdk --version  # Should be 2.x
  ```
- [ ] **Python 3.12+**
  ```bash
  python3 --version  # Should be 3.12 or higher
  ```
- [ ] **NASA FIRMS API Key**
  - Go to: https://firms.modaps.eosdis.nasa.gov/api/area/
  - Register for free account
  - Save your MAP_KEY

### Optional

- [ ] **BigDataCloud API Key** (free tier: 10K requests/month)
  - Go to: https://www.bigdatacloud.com/
  - Free tier works without key (rate limited)

---

## 🔧 Step-by-Step Deployment

### Step 1: Clone & Setup

```bash
# Navigate to project directory
cd firewatch

# Create Python virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# OR
.venv\Scripts\activate.bat  # Windows
```

### Step 2: Install Dependencies

```bash
# Install CDK dependencies
pip install -r requirements.txt

# Verify installation
pip list | grep aws-cdk
```

### Step 3: Configure AWS

```bash
# Configure AWS credentials (if not already done)
aws configure
# AWS Access Key ID: [Your Access Key]
# AWS Secret Access Key: [Your Secret Key]
# Default region name: us-east-1  # or your preferred region
# Default output format: json

# Verify credentials
aws sts get-caller-identity
```

### Step 4: Bootstrap CDK

**First-time setup only** - Creates S3 bucket for CDK assets:

```bash
cdk bootstrap aws://ACCOUNT-ID/REGION

# Example:
# cdk bootstrap aws://123456789012/us-east-1

# Or let CDK determine your account:
cdk bootstrap
```

Expected output:
```
✅  Environment aws://123456789012/us-east-1 bootstrapped
```

### Step 5: Review Changes

```bash
# Synthesize CloudFormation template
cdk synth

# View what will be created
cdk diff
```

This shows all resources that will be created.

### Step 6: Deploy Stack

```bash
# Deploy to AWS
cdk deploy

# Or skip confirmation prompts:
cdk deploy --require-approval never
```

**Deployment takes ~10-15 minutes** due to VPC, NAT Gateway, and VPC endpoints.

Expected output:
```
✅  FirewatchStack

Outputs:
FirewatchStack.QueueURL = https://sqs.us-east-1.amazonaws.com/...
FirewatchStack.TableName = firewatch-data
FirewatchStack.SNSTopicARN = arn:aws:sns:us-east-1:...
FirewatchStack.BigDataSecretARN = arn:aws:secretsmanager:us-east-1:...
FirewatchStack.FirmsSecretARN = arn:aws:secretsmanager:us-east-1:...
```

**Save these outputs!** You'll need them for configuration.

### Step 7: Update API Keys

#### Update NASA FIRMS API Key (REQUIRED)

```bash
# Replace YOUR_MAP_KEY with your actual NASA FIRMS key
aws secretsmanager update-secret \
  --secret-id firewatch/nasa-firms-api-key \
  --secret-string '{
    "api_key": "YOUR_MAP_KEY",
    "map_key": "YOUR_MAP_KEY"
  }'
```

#### Update BigDataCloud API Key (OPTIONAL)

```bash
# If you have a BigDataCloud API key:
aws secretsmanager update-secret \
  --secret-id firewatch/bigdatacloud-api-key \
  --secret-string '{
    "api_key": "YOUR_BIGDATA_KEY"
  }'

# If not, the free tier works without a key
```

### Step 8: Subscribe to Alerts (OPTIONAL)

```bash
# Get SNS Topic ARN from deployment outputs
SNS_TOPIC_ARN="<YOUR_SNS_TOPIC_ARN>"

# Subscribe your email
aws sns subscribe \
  --topic-arn $SNS_TOPIC_ARN \
  --protocol email \
  --notification-endpoint your-email@example.com

# Check your email and confirm subscription
```

### Step 9: Test the System

#### Trigger Fetch Lambda Manually

```bash
aws lambda invoke \
  --function-name firewatch-fetch-fires-api \
  --payload '{}' \
  response.json

# View response
cat response.json
```

Expected response:
```json
{
  "statusCode": 200,
  "body": "{\"message\": \"Fire data fetched successfully\", \"fires_found\": 42, \"fires_queued\": 42}"
}
```

#### Check Lambda Logs

```bash
# View fetch Lambda logs
aws logs tail /aws/lambda/firewatch-fetch-fires-api --follow

# View process Lambda logs
aws logs tail /aws/lambda/firewatch-process-fires --follow

# View stream Lambda logs
aws logs tail /aws/lambda/firewatch-stream-processor --follow
```

#### Query DynamoDB

```bash
# Count items in table
aws dynamodb scan \
  --table-name firewatch-data \
  --select "COUNT"

# Get first 10 fires
aws dynamodb scan \
  --table-name firewatch-data \
  --limit 10
```

---

## 🔍 Verification Checklist

After deployment, verify:

- [ ] **CloudFormation Stack** deployed successfully
  ```bash
  aws cloudformation describe-stacks --stack-name FirewatchStack
  ```

- [ ] **Lambda Functions** created (3 functions)
  ```bash
  aws lambda list-functions --query 'Functions[?contains(FunctionName, `firewatch`)].FunctionName'
  ```

- [ ] **DynamoDB Table** exists
  ```bash
  aws dynamodb describe-table --table-name firewatch-data
  ```

- [ ] **SQS Queues** created (2 queues)
  ```bash
  aws sqs list-queues | grep firewatch
  ```

- [ ] **Secrets** created (2 secrets)
  ```bash
  aws secretsmanager list-secrets --query 'SecretList[?contains(Name, `firewatch`)].Name'
  ```

- [ ] **EventBridge Rule** enabled
  ```bash
  aws events describe-rule --name firewatch-fetch-schedule
  ```

- [ ] **SNS Topic** created
  ```bash
  aws sns list-topics | grep firewatch
  ```

---

## 🎯 Post-Deployment Configuration

### Adjust Polling Frequency

Default: Every 15 minutes

To change:
1. Edit `firewatch/firewatch_stack.py`
2. Modify the schedule:
   ```python
   schedule=events.Schedule.rate(Duration.minutes(15))  # Change value
   ```
3. Redeploy:
   ```bash
   cdk deploy
   ```

### Change Geographic Area

Default: World

To change:
1. Edit `lambda/fetch_fires.py`
2. Modify `fetch_firms_data()` call:
   ```python
   fires = fetch_firms_data(
       map_key,
       area='USA',  # or 'California', etc.
   )
   ```
3. Redeploy Lambda:
   ```bash
   cdk deploy
   ```

### Add Email Notifications

```bash
# Subscribe multiple emails
aws sns subscribe \
  --topic-arn <SNS_TOPIC_ARN> \
  --protocol email \
  --notification-endpoint email1@example.com

aws sns subscribe \
  --topic-arn <SNS_TOPIC_ARN> \
  --protocol email \
  --notification-endpoint email2@example.com
```

### Add SMS Notifications

```bash
aws sns subscribe \
  --topic-arn <SNS_TOPIC_ARN> \
  --protocol sms \
  --notification-endpoint +1234567890
```

---

## 🐛 Troubleshooting

### CDK Bootstrap Failed

**Error**: `Need to perform AWS calls for account XXX, but no credentials found`

**Solution**:
```bash
aws configure
# Enter your AWS credentials
```

### Deployment Failed: VPC Limits

**Error**: `Maximum number of VPCs reached`

**Solution**: Delete unused VPCs or request limit increase:
```bash
aws ec2 describe-vpcs
aws ec2 delete-vpc --vpc-id vpc-xxx
```

### Lambda Not Executing

**Error**: No logs in CloudWatch

**Solution**:
1. Check EventBridge rule is enabled:
   ```bash
   aws events describe-rule --name firewatch-fetch-schedule
   ```
2. Enable if disabled:
   ```bash
   aws events enable-rule --name firewatch-fetch-schedule
   ```

### No Fires Detected

**Possible causes**:
1. ✅ **API key not updated** - Update in Secrets Manager
2. ✅ **No active fires** - Normal if no fires in selected area
3. ✅ **API rate limit** - Wait and try again

**Debug**:
```bash
# Check Lambda logs
aws logs tail /aws/lambda/firewatch-fetch-fires-api --follow

# Manually trigger
aws lambda invoke \
  --function-name firewatch-fetch-fires-api \
  --payload '{}' \
  response.json && cat response.json
```

### High Costs

**Check costs**:
```bash
# Open AWS Cost Explorer
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=SERVICE
```

**Main cost drivers**:
- NAT Gateway: ~$32/month (largest expense)
- VPC Endpoints: ~$7/month
- Lambda: ~$1/month (minimal)

**Reduce costs**:
- Decrease polling frequency (15 min → 1 hour)
- Use NAT instance instead of NAT Gateway
- Reduce VPC endpoints (remove Secrets Manager endpoint)

---

## 🔄 Updates & Maintenance

### Update Lambda Code

After modifying Lambda functions:

```bash
cdk deploy
```

CDK automatically detects changes and updates only modified Lambdas.

### View Stack Events

```bash
# Real-time events during deployment
aws cloudformation describe-stack-events \
  --stack-name FirewatchStack \
  --max-items 20
```

### Stack Drift Detection

Check if resources were modified outside CDK:

```bash
aws cloudformation detect-stack-drift --stack-name FirewatchStack

# View drift status
aws cloudformation describe-stack-resource-drifts --stack-name FirewatchStack
```

---

## 🗑️ Cleanup

### Delete All Resources

```bash
# Delete stack
cdk destroy

# Confirm deletion
# Type 'y' when prompted
```

**⚠️ Note**: DynamoDB table has `RemovalPolicy.RETAIN` and won't be deleted.

### Delete DynamoDB Table Manually

```bash
# WARNING: This deletes all fire data permanently
aws dynamodb delete-table --table-name firewatch-data
```

### Delete Secrets

```bash
# Delete secrets (optional)
aws secretsmanager delete-secret \
  --secret-id firewatch/bigdatacloud-api-key \
  --force-delete-without-recovery

aws secretsmanager delete-secret \
  --secret-id firewatch/nasa-firms-api-key \
  --force-delete-without-recovery
```

### Delete CDK Bootstrap (Advanced)

Only if you're done with CDK entirely:

```bash
# List CDK bootstrap stacks
aws cloudformation list-stacks | grep CDKToolkit

# Delete bootstrap stack
aws cloudformation delete-stack --stack-name CDKToolkit
```

---

## 📊 Monitoring Setup

### Create CloudWatch Dashboard

```bash
# Create dashboard for Firewatch metrics
aws cloudwatch put-dashboard \
  --dashboard-name Firewatch \
  --dashboard-body file://dashboard.json
```

Example `dashboard.json`:
```json
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/Lambda", "Invocations", {"stat": "Sum"}]
        ],
        "period": 300,
        "stat": "Sum",
        "region": "us-east-1",
        "title": "Lambda Invocations"
      }
    }
  ]
}
```

### Set Up Alarms

#### DLQ Messages Alarm

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name firewatch-dlq-messages \
  --alarm-description "Alert when messages in DLQ" \
  --metric-name ApproximateNumberOfMessagesVisible \
  --namespace AWS/SQS \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 1 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=QueueName,Value=firewatch-data-dlq
```

#### Lambda Errors Alarm

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name firewatch-lambda-errors \
  --alarm-description "Alert on Lambda errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=FunctionName,Value=firewatch-fetch-fires-api
```

---

## 🔐 Security Hardening

### Enable CloudTrail

```bash
aws cloudtrail create-trail \
  --name firewatch-trail \
  --s3-bucket-name my-cloudtrail-bucket

aws cloudtrail start-logging --name firewatch-trail
```

### Enable AWS Config

```bash
aws configservice put-configuration-recorder \
  --configuration-recorder name=default,roleARN=arn:aws:iam::ACCOUNT:role/config-role

aws configservice start-configuration-recorder --configuration-recorder-name default
```

### Enable GuardDuty

```bash
aws guardduty create-detector --enable
```

---

## 📞 Support & Resources

### AWS Documentation
- [AWS CDK](https://docs.aws.amazon.com/cdk/)
- [Lambda](https://docs.aws.amazon.com/lambda/)
- [DynamoDB](https://docs.aws.amazon.com/dynamodb/)
- [SQS](https://docs.aws.amazon.com/sqs/)

### NASA FIRMS
- [API Documentation](https://firms.modaps.eosdis.nasa.gov/api/)
- [Map Interface](https://firms.modaps.eosdis.nasa.gov/map/)

### Community
- GitHub Issues
- AWS Forums
- Stack Overflow (tag: aws-cdk)

---

**🎉 Congratulations! Your Firewatch system is now deployed and running!**

