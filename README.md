# Firewatch

**Secure, Scalable, Real-Time Wildfire Monitoring System**

Firewatch is a serverless AWS infrastructure that automatically fetches, processes, and stores wildfire data from NASA's FIRMS (Fire Information for Resource Management System) API. The system enriches fire coordinates with human-readable location data and provides real-time alerts.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FIREWATCH ARCHITECTURE                       │
└─────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐
    │ EventBridge  │   Every 15 minutes
    │   Schedule   │
    └──────┬───────┘
           │
           ▼
    ┌──────────────────────┐
    │  Lambda: Fetch Fires │   Fetches from NASA FIRMS API
    │  (fetch_fires.py)    │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │   SQS Queue (FIFO)   │   Decouples & Buffers
    │  + Dead Letter Queue │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────────┐
    │ Lambda: Process Fires    │   Geocodes with BigDataCloud
    │ (process_fires.py)       │
    └──────────┬───────────────┘
               │
               ▼
    ┌──────────────────────────┐
    │  DynamoDB Table          │   Stores enriched fire data
    │  (firewatch-data)        │     + DynamoDB Streams enabled
    │  - fire_id (PK)          │
    │  - timestamp (SK)        │
    │  - GSI: location-index   │
    └──────────┬───────────────┘
               │
               │ Stream
               ▼
    ┌──────────────────────────┐
    │ Lambda: Stream Processor │   Monitors changes
    │ (stream_processor.py)    │
    └──────────┬───────────────┘
               │
               ▼
    ┌──────────────────────────┐
    │   SNS Topic              │   Fire alerts & notifications
    │   (firewatch-alerts)     │
    └──────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                          SECURITY LAYER                              │
├─────────────────────────────────────────────────────────────────────┤
│   AWS Secrets Manager                                             │
│     - BigDataCloud API Key                                          │
│     - NASA FIRMS API Key                                            │
│                                                                      │
│   VPC Private Subnets                                             │
│     - All Lambdas run in isolated subnets                           │
│     - VPC Endpoints for DynamoDB, S3, Secrets Manager               │
│     - NAT Gateway for external API calls                            │
│                                                                     |
│   IAM Least Privilege                                             |
│     - Function-specific roles                                       │
│     - No hardcoded credentials                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

### 🔐 Security First
- **Secrets Manager**: API keys stored securely, never in code
- **VPC Isolation**: All Lambda functions run in private subnets
- **VPC Endpoints**: Cost-optimized, secure access to AWS services
- **IAM Least Privilege**: Each function has only the permissions it needs
- **Point-in-Time Recovery**: DynamoDB backup enabled

### 📈 Scalable & Reliable
- **SQS Decoupling**: Handles burst traffic, automatic retries
- **Dead Letter Queue**: Failed messages captured for analysis
- **Concurrent Limits**: Prevents API throttling
- **Batch Processing**: Efficient handling of multiple fires
- **Deduplication**: Prevents duplicate fire records

### 🔄 Real-Time Sync
- **EventBridge Schedule**: Automatic polling every 15 minutes (configurable)
- **DynamoDB Streams**: Real-time change detection
- **SNS Notifications**: Instant alerts for new fires
- **Stream Processing**: Monitor all database changes

### 🌍 Location Enrichment
- **Reverse Geocoding**: Converts coordinates to human-readable locations
- **BigDataCloud API**: City, state, country information
- **GSI Index**: Fast queries by country/region

---

## 🚀 Deployment

### Prerequisites

1. **AWS Account** with appropriate permissions
2. **AWS CDK** installed: `npm install -g aws-cdk`
3. **Python 3.12+** installed
4. **NASA FIRMS API Key**: Get yours at [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/api/area/)
5. **BigDataCloud API Key** (optional, free tier works without key)

### Setup

1. **Clone the repository**
   ```bash
   cd firewatch
   ```

2. **Create and activate virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate.bat
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Bootstrap CDK (first time only)**
   ```bash
   cdk bootstrap
   ```

5. **Synthesize CloudFormation template**
   ```bash
   cdk synth
   ```

6. **Deploy the stack**
   ```bash
   cdk deploy
   ```

   This will create:
   - VPC with public/private subnets
   - 3 Lambda functions
   - DynamoDB table
   - SQS queues
   - SNS topic
   - Secrets Manager secrets
   - EventBridge schedule
   - All necessary IAM roles and policies

7. **Update API Keys in Secrets Manager**

   After deployment, update the secrets with your actual API keys:

   ```bash
   # Update NASA FIRMS API Key
   aws secretsmanager update-secret \
     --secret-id firewatch/nasa-firms-api-key \
     --secret-string '{"api_key":"YOUR_FIRMS_KEY","map_key":"YOUR_MAP_KEY"}'

   # Update BigDataCloud API Key (optional)
   aws secretsmanager update-secret \
     --secret-id firewatch/bigdatacloud-api-key \
     --secret-string '{"api_key":"YOUR_BIGDATA_KEY"}'
   ```

8. **Subscribe to SNS Notifications** (optional)

   ```bash
   aws sns subscribe \
     --topic-arn <SNS_TOPIC_ARN_FROM_OUTPUT> \
     --protocol email \
     --notification-endpoint your-email@example.com
   ```

   Confirm the subscription via the email you receive.

---

## 📊 Data Flow

### 1. **Fetch Phase** (fetch_fires.py)
- Triggered by EventBridge every 15 minutes
- Calls NASA FIRMS API for fires in last 24 hours
- Batches fires (10 per message)
- Sends to SQS queue

### 2. **Process Phase** (process_fires.py)
- Triggered by SQS messages
- For each fire:
  - Validates coordinates
  - Calls BigDataCloud for reverse geocoding
  - Creates unique fire_id to prevent duplicates
  - Stores in DynamoDB
- Automatic retry on failure

### 3. **Monitor Phase** (stream_processor.py)
- Triggered by DynamoDB Streams
- Detects new fires (INSERT events)
- Groups by country
- Sends formatted alerts to SNS

---

## 🗄️ Data Schema

### DynamoDB Table: `firewatch-data`

```python
{
  "fire_id": "37.7749_-122.4194_2024-01-15_1430",  # PK
  "timestamp": 1705329000,                          # SK (Unix timestamp)
  "latitude": 37.7749,
  "longitude": -122.4194,
  "brightness": 320.5,                              # Kelvin
  "confidence": "high",                             # low/nominal/high
  "frp": 15.3,                                      # Fire Radiative Power (MW)
  "acq_date": "2024-01-15",
  "acq_time": "1430",
  "satellite": "Suomi-NPP",
  "instrument": "VIIRS",
  "daynight": "D",
  "location_city": "San Francisco",
  "location_locality": "San Francisco County",
  "location_state": "California",
  "location_country": "United States of America",
  "created_at": "2024-01-15T14:30:00Z"
}
```

### Global Secondary Index: `location-index`
- **Partition Key**: `location_country`
- **Sort Key**: `timestamp`
- **Use case**: Query all fires by country/region

---

## 🔧 Configuration

### Adjust Polling Frequency

Edit `firewatch_stack.py`:

```python
schedule_rule = events.Rule(
    self, "FetchFiresSchedule",
    schedule=events.Schedule.rate(Duration.minutes(15)),  # Change this
)
```

Options:
- `Duration.minutes(5)` - Every 5 minutes (more real-time)
- `Duration.hours(1)` - Every hour (less frequent)
- `events.Schedule.cron(minute='0', hour='*/6')` - Every 6 hours

### Change Geographic Area

Edit `lambda/fetch_fires.py`:

```python
fires = fetch_firms_data(
    map_key,
    source='VIIRS_SNPP_NRT',  # VIIRS_SNPP_NRT, VIIRS_NOAA20_NRT, MODIS_NRT
    area='world',              # world, USA, California, etc.
    day_range=1               # 1-10 days
)
```

### Adjust Batch Size

Edit `firewatch_stack.py`:

```python
process_lambda.add_event_source(
    lambda_events.SqsEventSource(
        fire_data_queue,
        batch_size=10,  # 1-10 for standard queue
    )
)
```

---

## 📈 Monitoring & Observability

### CloudWatch Logs

Each Lambda function writes logs to CloudWatch:
- `/aws/lambda/firewatch-fetch-fires-api`
- `/aws/lambda/firewatch-process-fires`
- `/aws/lambda/firewatch-stream-processor`

### Metrics to Monitor

1. **Fetch Lambda**:
   - Invocations
   - Duration
   - Errors
   - SQS messages sent

2. **Process Lambda**:
   - SQS messages processed
   - DynamoDB write capacity
   - Geocoding API errors

3. **DynamoDB**:
   - Read/Write capacity units
   - Throttled requests
   - Item count

4. **SQS**:
   - Messages in queue
   - Messages in DLQ (investigate if > 0)
   - Age of oldest message

### Set Up Alarms

```bash
# Example: Alert on DLQ messages
aws cloudwatch put-metric-alarm \
  --alarm-name firewatch-dlq-messages \
  --alarm-description "Alert when messages in DLQ" \
  --metric-name ApproximateNumberOfMessagesVisible \
  --namespace AWS/SQS \
  --statistic Average \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 1 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=QueueName,Value=firewatch-data-dlq
```

---

##  Cost Estimate

### Monthly Costs (Approximate)

| Service | Usage | Cost |
|---------|-------|------|
| **NAT Gateway** | 730 hours | ~$32.00 |
| **Lambda** | ~3,000 invocations | ~$0.50 |
| **DynamoDB** | Pay-per-request | ~$1.25 (1M writes) |
| **SQS** | 1M requests | ~$0.40 |
| **Secrets Manager** | 2 secrets | ~$0.80 |
| **VPC Endpoints** | Interface endpoints | ~$7.30 |
| **Data Transfer** | API calls | ~$1.00 |
| **CloudWatch Logs** | Log storage | ~$0.50 |
| **SNS** | Notifications | ~$0.01 |
| **TOTAL** | | **~$43.76/month** |

### Cost Optimization Tips

1. **Reduce NAT Gateway costs**:
   - Use VPC endpoints for AWS services (already implemented)
   - Consider NAT instances for lower traffic

2. **Optimize Lambda**:
   - Reduce memory allocation if not needed
   - Decrease polling frequency
   - Use reserved concurrency wisely

3. **DynamoDB**:
   - Use on-demand billing (already set)
   - Enable auto-scaling if switching to provisioned
   - Set TTL for old records

4. **SQS**:
   - Already using standard queue (cheaper than FIFO)

---

## 🧪 Testing

### Test Fetch Lambda Locally

```bash
# Invoke fetch function manually
aws lambda invoke \
  --function-name firewatch-fetch-fires-api \
  --payload '{}' \
  response.json

cat response.json
```

### Test Process Lambda

```bash
# Send test fire to SQS
aws sqs send-message \
  --queue-url <QUEUE_URL> \
  --message-body '{
    "fires": [{
      "latitude": 37.7749,
      "longitude": -122.4194,
      "brightness": 320,
      "confidence": "high",
      "frp": 15.3
    }]
  }'
```

### Query DynamoDB

```bash
# Scan table
aws dynamodb scan \
  --table-name firewatch-data \
  --limit 10

# Query by country
aws dynamodb query \
  --table-name firewatch-data \
  --index-name location-index \
  --key-condition-expression "location_country = :country" \
  --expression-attribute-values '{":country":{"S":"United States of America"}}'
```

---

## 🔒 Security Best Practices

✅ **Implemented**:
- API keys in Secrets Manager
- VPC isolation for Lambda
- VPC endpoints for AWS services
- IAM least privilege
- No hardcoded credentials
- Point-in-time recovery for DynamoDB
- Encrypted data at rest (DynamoDB default)
- VPC Flow Logs enabled

📋 **Additional Recommendations**:
- Enable AWS CloudTrail for audit logging
- Set up AWS Config for compliance monitoring
- Use AWS KMS for custom encryption keys
- Implement API Gateway with authentication for data access
- Add AWS WAF if exposing public endpoints
- Enable GuardDuty for threat detection

---

## 🐛 Troubleshooting

### No fires being detected

1. Check EventBridge rule is enabled:
   ```bash
   aws events describe-rule --name firewatch-fetch-schedule
   ```

2. Check fetch Lambda logs:
   ```bash
   aws logs tail /aws/lambda/firewatch-fetch-fires-api --follow
   ```

3. Verify NASA FIRMS API key is correct in Secrets Manager

### Fires not appearing in DynamoDB

1. Check SQS queue for messages:
   ```bash
   aws sqs get-queue-attributes \
     --queue-url <QUEUE_URL> \
     --attribute-names ApproximateNumberOfMessages
   ```

2. Check DLQ for failed messages:
   ```bash
   aws sqs receive-message --queue-url <DLQ_URL>
   ```

3. Check process Lambda logs for errors

### High costs

1. Check NAT Gateway data transfer:
   ```bash
   aws cloudwatch get-metric-statistics \
     --namespace AWS/NATGateway \
     --metric-name BytesOutToDestination \
     --dimensions Name=NatGatewayId,Value=<NAT_ID> \
     --start-time 2024-01-01T00:00:00Z \
     --end-time 2024-01-31T23:59:59Z \
     --period 86400 \
     --statistics Sum
   ```

2. Review Lambda concurrent executions
3. Check DynamoDB read/write capacity

---

## 🛠️ Development

### Project Structure

```
firewatch/
├── app.py                      # CDK app entry point
├── firewatch_stack.py          # Main CDK stack definition
├── cdk.json                    # CDK configuration
├── requirements.txt            # Python dependencies
├── README.md                   # This file
├── lambda/                     # Lambda function code
│   ├── fetch_fires.py         # Fetch from NASA FIRMS
│   ├── process_fires.py       # Process & geocode
│   ├── stream_processor.py    # DynamoDB Streams handler
│   ├── lambda_function.py     # Legacy function (keep for reference)
│   └── requirements.txt       # Lambda dependencies
└── tests/                      # Unit tests
    └── unit/
        └── test_firewatch_stack.py
```

### Running Tests

```bash
pytest tests/
```

### Cleanup

To delete all resources:

```bash
cdk destroy
```

⚠️ **Note**: DynamoDB table has `RemovalPolicy.RETAIN` and will not be deleted. Delete manually if needed:

```bash
aws dynamodb delete-table --table-name firewatch-data
```

---

## 📚 API Documentation

### NASA FIRMS API

- **Documentation**: https://firms.modaps.eosdis.nasa.gov/api/
- **Get API Key**: https://firms.modaps.eosdis.nasa.gov/api/area/
- **Data Sources**:
  - VIIRS S-NPP (375m resolution)
  - VIIRS NOAA-20 (375m resolution)
  - MODIS (1km resolution)

### BigDataCloud API

- **Documentation**: https://www.bigdatacloud.com/docs/api/free-reverse-geocode-to-city-api
- **Free Tier**: 10,000 requests/month
- **No key required**: Works without API key (rate-limited)

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

---

## 📝 License

This project is provided as-is for educational and monitoring purposes.

---

## 🙏 Acknowledgments

- **NASA FIRMS**: For providing free, real-time wildfire data
- **BigDataCloud**: For reverse geocoding services
- **AWS CDK**: For infrastructure as code
- **Community**: For feedback and contributions

---

## 📞 Support

For issues, questions, or contributions:
- Open an issue on GitHub
- Check CloudWatch logs for errors
- Review AWS documentation for service limits

---

**Built with ❤️ for wildfire awareness and monitoring**
