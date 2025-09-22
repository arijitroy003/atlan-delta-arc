# AWS Lambda Deployment Guide
**Converting Atlan Delta Arc to Serverless Architecture**

## 🚀 Overview

This guide outlines how to deploy the Atlan Delta Arc data lineage pipeline as an AWS Lambda function, enabling scheduled execution on serverless compute with cost-effective, scalable automation.

## 📋 Current vs. Lambda Architecture

### Current Architecture
```
[Local Python Script] → [Atlan API] → [S3 Bucket] → [Cache Files]
```

### Target Lambda Architecture
```
[CloudWatch Events] → [Lambda Function] → [Atlan API] → [S3 Bucket]
                              ↓
                      [S3 Cache Storage] ← [Environment Variables]
```

## 🔧 Implementation Steps

### 1. Code Modifications for Lambda

#### A. Lambda Handler Function
Create a new `lambda_handler.py`:

```python
import json
import os
import boto3
from main import (
    find_postgres_assets,
    find_snowflake_assets,
    integration_with_S3,
    create_table_lineage,
    create_column_lineage
)

def lambda_handler(event, context):
    """
    AWS Lambda handler for Atlan data lineage pipeline
    """
    try:
        # Initialize from environment variables
        setup_environment()

        # Execute the pipeline
        result = execute_lineage_pipeline(event)

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Pipeline executed successfully',
                'result': result
            })
        }

    except Exception as e:
        print(f"❌ Lambda execution failed: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'message': 'Pipeline execution failed'
            })
        }

def setup_environment():
    """Configure environment for Lambda execution"""
    global ATLAN_BASE_URL, ATLAN_API_TOKEN, S3_BUCKET_NAME

    ATLAN_BASE_URL = os.environ['ATLAN_BASE_URL']
    ATLAN_API_TOKEN = os.environ['ATLAN_API_TOKEN']
    S3_BUCKET_NAME = os.environ['S3_BUCKET_NAME']
    # ... other environment variables

def execute_lineage_pipeline(event):
    """Execute the main pipeline logic"""
    # Get assets (cache will be in S3)
    postgres_assets = find_postgres_assets()
    snowflake_assets = find_snowflake_assets()

    # S3 integration
    s3_result = integration_with_S3()

    # Create lineage
    create_table_lineage(postgres_assets, s3_result['s3_objects'], snowflake_assets)
    create_column_lineage(postgres_assets, snowflake_assets)

    return {
        'postgres_assets_count': len(postgres_assets),
        'snowflake_assets_count': len(snowflake_assets),
        's3_objects_count': len(s3_result['s3_objects'])
    }
```

#### B. Cache Storage Modification
Replace local JSON files with S3 storage:

```python
import boto3
from botocore.exceptions import ClientError

class S3CacheManager:
    def __init__(self, bucket_name, cache_prefix='cache/'):
        self.s3_client = boto3.client('s3')
        self.bucket_name = bucket_name
        self.cache_prefix = cache_prefix

    def load_cache_from_s3(self, cache_key):
        """Load cache from S3"""
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=f"{self.cache_prefix}{cache_key}"
            )
            return json.loads(response['Body'].read())
        except ClientError:
            return None

    def save_cache_to_s3(self, data, cache_key):
        """Save cache to S3"""
        cache_data = {
            "timestamp": datetime.now().isoformat(),
            "data": data
        }

        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=f"{self.cache_prefix}{cache_key}",
            Body=json.dumps(cache_data),
            ContentType='application/json'
        )

    def is_cache_valid(self, cache_key, max_age_hours=24):
        """Check cache validity from S3"""
        cache_data = self.load_cache_from_s3(cache_key)
        if not cache_data:
            return False

        cache_time = datetime.fromisoformat(cache_data['timestamp'])
        expiry_time = cache_time + timedelta(hours=max_age_hours)
        return datetime.now() < expiry_time
```

### 2. Deployment Package Creation

#### A. Requirements for Lambda
Create `requirements-lambda.txt`:

```txt
pyatlan==2.0.0
boto3==1.34.0
requests==2.31.0
python-dotenv==1.0.0
```

#### B. Build Script
Create `build_lambda.sh`:

```bash
#!/bin/bash

# Create deployment package
rm -rf lambda-package
mkdir lambda-package

# Install dependencies
pip install -r requirements-lambda.txt -t lambda-package/

# Copy source code
cp lambda_handler.py lambda-package/
cp main.py lambda-package/
cp -r src/ lambda-package/ 2>/dev/null || true

# Create ZIP package
cd lambda-package
zip -r ../atlan-delta-arc-lambda.zip .
cd ..

echo "✅ Lambda package created: atlan-delta-arc-lambda.zip"
```

### 3. AWS Infrastructure Setup

#### A. Lambda Function Configuration
```yaml
# terraform/lambda.tf
resource "aws_lambda_function" "atlan_lineage" {
  filename         = "atlan-delta-arc-lambda.zip"
  function_name    = "atlan-delta-arc-pipeline"
  role            = aws_iam_role.lambda_execution.arn
  handler         = "lambda_handler.lambda_handler"
  runtime         = "python3.9"
  timeout         = 900  # 15 minutes
  memory_size     = 1024

  environment {
    variables = {
      ATLAN_BASE_URL           = var.atlan_base_url
      ATLAN_API_TOKEN         = var.atlan_api_token
      S3_BUCKET_NAME          = var.s3_bucket_name
      S3_BUCKET_ARN           = var.s3_bucket_arn
      S3_CONNECTION_NAME      = var.s3_connection_name
      S3_PREFIX               = var.s3_prefix
      POSTGRES_CONNECTION_NAME = var.postgres_connection_name
      SNOWFLAKE_CONNECTION_NAME = var.snowflake_connection_name
      CACHE_EXPIRY_HOURS      = "24"
      CACHE_S3_BUCKET         = var.cache_s3_bucket
    }
  }
}
```

#### B. IAM Role and Policies
```yaml
# terraform/iam.tf
resource "aws_iam_role" "lambda_execution" {
  name = "atlan-lambda-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_s3_policy" {
  name = "atlan-lambda-s3-policy"
  role = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.s3_bucket_name}/*",
          "arn:aws:s3:::${var.cache_s3_bucket}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}
```

#### C. CloudWatch Events for Scheduling
```yaml
# terraform/scheduling.tf
resource "aws_cloudwatch_event_rule" "daily_lineage" {
  name                = "atlan-daily-lineage"
  description         = "Trigger Atlan lineage pipeline daily"
  schedule_expression = "cron(0 2 * * ? *)"  # 2 AM UTC daily
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.daily_lineage.name
  target_id = "AtlanLineageLambdaTarget"
  arn       = aws_lambda_function.atlan_lineage.arn

  input = jsonencode({
    "trigger": "scheduled",
    "force_refresh": false
  })
}

resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.atlan_lineage.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_lineage.arn
}
```

### 4. Deployment Commands

#### A. Using AWS CLI
```bash
# Build package
./build_lambda.sh

# Deploy function
aws lambda create-function \
    --function-name atlan-delta-arc-pipeline \
    --runtime python3.9 \
    --role arn:aws:iam::ACCOUNT:role/lambda-execution-role \
    --handler lambda_handler.lambda_handler \
    --zip-file fileb://atlan-delta-arc-lambda.zip \
    --timeout 900 \
    --memory-size 1024

# Set environment variables
aws lambda update-function-configuration \
    --function-name atlan-delta-arc-pipeline \
    --environment Variables='{
        "ATLAN_BASE_URL":"https://your-tenant.atlan.com",
        "ATLAN_API_TOKEN":"your-token",
        "S3_BUCKET_NAME":"atlan-tech-challenge"
    }'
```

#### B. Using Terraform
```bash
# Initialize Terraform
terraform init

# Plan deployment
terraform plan -var-file="production.tfvars"

# Deploy infrastructure
terraform apply -var-file="production.tfvars"
```

## 📊 Monitoring and Observability

### CloudWatch Dashboards
```python
# Create monitoring dashboard
import boto3

cloudwatch = boto3.client('cloudwatch')

def create_lambda_dashboard():
    dashboard_body = {
        "widgets": [
            {
                "type": "metric",
                "properties": {
                    "metrics": [
                        ["AWS/Lambda", "Duration", "FunctionName", "atlan-delta-arc-pipeline"],
                        [".", "Errors", ".", "."],
                        [".", "Invocations", ".", "."]
                    ],
                    "period": 300,
                    "stat": "Average",
                    "region": "us-east-1",
                    "title": "Atlan Pipeline Lambda Metrics"
                }
            }
        ]
    }

    cloudwatch.put_dashboard(
        DashboardName='AtlanLineagePipeline',
        DashboardBody=json.dumps(dashboard_body)
    )
```

### Custom Metrics
```python
# Add to lambda_handler.py
import boto3

cloudwatch = boto3.client('cloudwatch')

def publish_custom_metrics(postgres_count, snowflake_count, s3_count):
    """Publish pipeline metrics to CloudWatch"""

    metrics = [
        {
            'MetricName': 'PostgreSQLAssetsProcessed',
            'Value': postgres_count,
            'Unit': 'Count'
        },
        {
            'MetricName': 'SnowflakeAssetsProcessed',
            'Value': snowflake_count,
            'Unit': 'Count'
        },
        {
            'MetricName': 'S3ObjectsCreated',
            'Value': s3_count,
            'Unit': 'Count'
        }
    ]

    cloudwatch.put_metric_data(
        Namespace='Atlan/LineagePipeline',
        MetricData=metrics
    )
```

## 💰 Cost Optimization

### Lambda Pricing Considerations
- **Free Tier**: 1M requests + 400,000 GB-seconds per month
- **Memory**: Optimize based on actual usage (start with 1024MB)
- **Timeout**: Set to minimum required (test with 15 minutes)
- **Frequency**: Daily execution = ~30 invocations/month

### Estimated Monthly Costs
```
Scenario: Daily execution, 5-minute duration, 1024MB memory

Lambda Costs:
- Invocations: 30 × $0.0000002 = $0.000006
- Duration: 30 × 5min × 1024MB × $0.0000166667 = $2.56
- Total: ~$2.56/month

S3 Costs (cache storage):
- Storage: ~1MB cache files = $0.023/month
- Requests: ~60 PUT/GET requests = $0.0002/month

Total Monthly Cost: ~$2.60
```

## 🔄 Scheduling Options

### 1. CloudWatch Events (EventBridge)
```bash
# Daily at 2 AM UTC
schedule_expression = "cron(0 2 * * ? *)"

# Every 6 hours
schedule_expression = "rate(6 hours)"

# Business hours only (9 AM Mon-Fri)
schedule_expression = "cron(0 9 ? * MON-FRI *)"
```

### 2. Event-Driven Triggers
```python
# S3 event trigger for new data files
{
    "Rules": [{
        "Name": "atlan-s3-trigger",
        "EventPattern": {
            "source": ["aws.s3"],
            "detail-type": ["Object Created"],
            "detail": {
                "bucket": {"name": ["atlan-tech-challenge"]},
                "object": {"key": [{"prefix": "2025/"}]}
            }
        },
        "Targets": [{
            "Id": "1",
            "Arn": "arn:aws:lambda:region:account:function:atlan-delta-arc-pipeline"
        }]
    }]
}
```

### 3. Manual Triggers
```bash
# Test invocation
aws lambda invoke \
    --function-name atlan-delta-arc-pipeline \
    --payload '{"trigger":"manual","force_refresh":true}' \
    response.json
```

## 🚨 Error Handling and Alerting

### SNS Notifications
```python
# Add to lambda_handler.py
import boto3

sns = boto3.client('sns')

def send_failure_notification(error_message):
    """Send failure notification via SNS"""
    sns.publish(
        TopicArn='arn:aws:sns:region:account:atlan-pipeline-alerts',
        Message=f"Atlan Pipeline Failed: {error_message}",
        Subject="Atlan Data Lineage Pipeline Failure"
    )

def lambda_handler(event, context):
    try:
        # Pipeline execution
        result = execute_lineage_pipeline(event)
        return success_response(result)

    except Exception as e:
        send_failure_notification(str(e))
        return error_response(e)
```

### CloudWatch Alarms
```yaml
# terraform/alarms.tf
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "atlan-lambda-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "1"
  alarm_description   = "This metric monitors lambda errors"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = aws_lambda_function.atlan_lineage.function_name
  }
}
```

## 📈 Benefits of Lambda Deployment

### Operational Benefits
- ✅ **Zero Infrastructure Management**: No servers to maintain
- ✅ **Automatic Scaling**: Handles concurrent executions automatically
- ✅ **Cost Effective**: Pay only for execution time
- ✅ **High Availability**: Built-in redundancy across AZs

### Business Benefits
- ✅ **Scheduled Automation**: Consistent lineage updates
- ✅ **Event-Driven Processing**: React to data changes immediately
- ✅ **Centralized Monitoring**: CloudWatch integration
- ✅ **Enterprise Security**: IAM-based access control

## 🔧 Migration Checklist

- [ ] Modify code for Lambda handler pattern
- [ ] Replace local file caching with S3 storage
- [ ] Create deployment package and dependencies
- [ ] Set up IAM roles and policies
- [ ] Configure environment variables
- [ ] Deploy Lambda function
- [ ] Set up CloudWatch scheduling
- [ ] Configure monitoring and alerting
- [ ] Test execution and validate results
- [ ] Set up backup and recovery procedures

---

**Next Steps:**
1. Review and adapt code modifications
2. Set up AWS infrastructure
3. Deploy and test Lambda function
4. Configure monitoring and alerting
5. Schedule production runs

*This serverless approach transforms the Atlan lineage pipeline into a fully managed, cost-effective, and scalable solution.*