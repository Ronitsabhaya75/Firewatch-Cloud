from aws_cdk import (
    Stack,
    SecretValue,
    aws_ec2 as ec2,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_lambda_event_sources as lambda_events,
    aws_iam as iam,
    aws_sqs as sqs,
    aws_secretsmanager as secretsmanager,
    aws_events as events,
    aws_events_targets as targets,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subscriptions,
    RemovalPolicy,
    Duration,
    CfnOutput,
)
from constructs import Construct
import json
import os

class FirewatchStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ============================================================
        # 1. SECRETS MANAGER - Secure API Key Storage
        # ============================================================
        
        # Store BigDataCloud API Key securely
        # Get from environment variable or use placeholder
        bigdata_api_key = os.environ.get('BIGDATA_API_KEY', 'YOUR_BIGDATA_API_KEY_HERE')
        bigdata_secret = secretsmanager.Secret(
            self, "BigDataCloudAPIKey",
            secret_name="firewatch/bigdatacloud-api-key",
            description="BigDataCloud API key for reverse geocoding",
            secret_string_value=SecretValue.unsafe_plain_text(
                json.dumps({
                    "api_key": bigdata_api_key
                })
            )
        )
        
        # Store NASA FIRMS API Key
        # Get from environment variable or use placeholder
        firms_api_key = os.environ.get('FIRMS_API_KEY', 'YOUR_FIRMS_API_KEY_HERE')
        firms_secret = secretsmanager.Secret(
            self, "NASAFirmsAPIKey",
            secret_name="firewatch/nasa-firms-api-key",
            description="NASA FIRMS API key for fire data",
            secret_string_value=SecretValue.unsafe_plain_text(
                json.dumps({
                    "api_key": firms_api_key,
                    "map_key": firms_api_key
                })
            )
        )

        # ============================================================
        # 2. VPC INFRASTRUCTURE
        # ============================================================
        
        vpc = ec2.Vpc(
            self, "FirewatchVPC",
            vpc_name="firewatch-vpc",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=3,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        # VPC Endpoints for cost optimization
        vpc.add_gateway_endpoint(
            "DynamoDBEndpoint",
            service=ec2.GatewayVpcEndpointAwsService.DYNAMODB,
        )
        
        vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )
        
        # Add Secrets Manager VPC Endpoint (interface endpoint)
        vpc.add_interface_endpoint(
            "SecretsManagerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
        )

        # ============================================================
        # 3. DYNAMODB TABLE with Streams
        # ============================================================
        
        # Import existing DynamoDB table with stream enabled
        table = dynamodb.Table.from_table_attributes(
            self, "FirewatchDataTable",
            table_name="firewatch-data",
            table_stream_arn="arn:aws:dynamodb:us-east-2:127214181284:table/firewatch-data/stream/2025-11-12T21:01:59.919"
        )

        # ============================================================
        # 4. SQS QUEUES - Decoupling & Reliability
        # ============================================================
        
        # Dead Letter Queue for failed messages
        dlq = sqs.Queue(
            self, "FireDataDLQ",
            queue_name="firewatch-data-dlq",
            retention_period=Duration.days(14),
        )
        
        # Main processing queue
        fire_data_queue = sqs.Queue(
            self, "FireDataQueue",
            queue_name="firewatch-data-queue",
            visibility_timeout=Duration.minutes(6),  # 3x Lambda timeout
            retention_period=Duration.days(4),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=dlq
            ),
        )

        # ============================================================
        # 5. SNS TOPIC - Notifications for new fires
        # ============================================================
        
        fire_alerts_topic = sns.Topic(
            self, "FireAlertsTopic",
            topic_name="firewatch-alerts",
            display_name="Firewatch Fire Alerts",
        )

        # ============================================================
        # 6. LAMBDA FUNCTIONS
        # ============================================================
        
        # Lambda 1: Fetch fires from NASA FIRMS API
        fetch_lambda = lambda_.Function(
            self, "FetchFiresFunction",
            function_name="firewatch-fetch-fires-api",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="fetch_fires.lambda_handler",
            code=lambda_.Code.from_asset("lambda"),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            timeout=Duration.minutes(2),
            memory_size=512,
            environment={
                "QUEUE_URL": fire_data_queue.queue_url,
                "FIRMS_SECRET_NAME": firms_secret.secret_name,
            },
        )
        
        # Lambda 2: Process fires (geocode + store)
        process_lambda = lambda_.Function(
            self, "ProcessFiresFunction",
            function_name="firewatch-process-fires",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="process_fires.lambda_handler",
            code=lambda_.Code.from_asset("lambda"),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            timeout=Duration.minutes(2),
            memory_size=256,
            environment={
                "DYNAMODB_TABLE_NAME": table.table_name,
                "BIGDATA_SECRET_NAME": bigdata_secret.secret_name,
            },
        )
        
        # Lambda 3: Stream processor for monitoring changes
        stream_lambda = lambda_.Function(
            self, "StreamProcessorFunction",
            function_name="firewatch-stream-processor",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="stream_processor.lambda_handler",
            code=lambda_.Code.from_asset("lambda"),
            timeout=Duration.minutes(1),
            memory_size=128,
            environment={
                "SNS_TOPIC_ARN": fire_alerts_topic.topic_arn,
            },
        )

        # ============================================================
        # 7. EVENT SOURCES & TRIGGERS
        # ============================================================
        
        # Connect SQS to processing Lambda
        process_lambda.add_event_source(
            lambda_events.SqsEventSource(
                fire_data_queue,
                batch_size=10,  # Process 10 fires at a time
                max_batching_window=Duration.seconds(10),
            )
        )
        
        # Connect DynamoDB Stream to monitoring Lambda
        stream_lambda.add_event_source(
            lambda_events.DynamoEventSource(
                table,
                starting_position=lambda_.StartingPosition.LATEST,
                batch_size=100,
                bisect_batch_on_error=True,
                retry_attempts=2,
            )
        )
        
        # EventBridge rule: Run every 15 minutes
        schedule_rule = events.Rule(
            self, "FetchFiresSchedule",
            rule_name="firewatch-fetch-schedule",
            schedule=events.Schedule.rate(Duration.minutes(15)),  # Adjust frequency
            description="Fetch fire data from NASA FIRMS every 15 minutes",
        )
        
        schedule_rule.add_target(
            targets.LambdaFunction(fetch_lambda)
        )

        # ============================================================
        # 8. IAM PERMISSIONS
        # ============================================================
        
        # Grant fetch Lambda permissions
        fire_data_queue.grant_send_messages(fetch_lambda)
        firms_secret.grant_read(fetch_lambda)
        
        # Grant process Lambda permissions
        table.grant_read_write_data(process_lambda)
        bigdata_secret.grant_read(process_lambda)
        
        # Grant stream Lambda permissions
        fire_alerts_topic.grant_publish(stream_lambda)
        
        # VPC Flow Logs
        ec2.FlowLog(
            self, "FirewatchVPCFlowLog",
            resource_type=ec2.FlowLogResourceType.from_vpc(vpc)
        )

        # ============================================================
        # 9. OUTPUTS
        # ============================================================
        
        CfnOutput(
            self, "QueueURL",
            value=fire_data_queue.queue_url,
            description="SQS Queue URL for fire data"
        )
        
        CfnOutput(
            self, "TableName",
            value=table.table_name,
            description="DynamoDB table name"
        )
        
        CfnOutput(
            self, "SNSTopicARN",
            value=fire_alerts_topic.topic_arn,
            description="SNS Topic ARN for fire alerts"
        )
        
        CfnOutput(
            self, "BigDataSecretARN",
            value=bigdata_secret.secret_arn,
            description="BigDataCloud API Key Secret ARN"
        )
        
        CfnOutput(
            self, "FirmsSecretARN",
            value=firms_secret.secret_arn,
            description="NASA FIRMS API Key Secret ARN"
        )
