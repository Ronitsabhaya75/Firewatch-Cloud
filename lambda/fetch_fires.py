"""
Lambda function to fetch fire data from NASA FIRMS API
Runs on a schedule (EventBridge) and sends data to SQS for processing
"""
import json
import urllib.request
import urllib.parse
import os
import boto3
from datetime import datetime, timedelta

# Initialize AWS services
sqs = boto3.client('sqs')
secretsmanager = boto3.client('secretsmanager')

QUEUE_URL = os.environ['QUEUE_URL']
FIRMS_SECRET_NAME = os.environ['FIRMS_SECRET_NAME']

def lambda_handler(event, context):
    """
    Fetch active fire data from NASA FIRMS and send to SQS for processing
    """
    try:
        print("🔥 Starting fire data fetch from NASA FIRMS...")
        
        # Get API credentials from Secrets Manager
        secret = get_secret(FIRMS_SECRET_NAME)
        map_key = secret.get('map_key')
        
        if not map_key or map_key == "YOUR_MAP_KEY_HERE":
            print("⚠️  NASA FIRMS API key not configured. Please update the secret.")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'NASA FIRMS API key not configured',
                    'message': 'Please update the secret with your FIRMS map key'
                })
            }
        
        # Fetch fires from the last 24 hours
        fires = fetch_firms_data(map_key)
        
        if not fires:
            print("ℹ️  No active fires detected in the last 24 hours")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'No active fires detected',
                    'fires_found': 0
                })
            }
        
        # Send fires to SQS queue in batches
        sent_count = send_to_queue(fires)
        
        print(f"✅ Successfully sent {sent_count} fires to processing queue")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Fire data fetched successfully',
                'fires_found': len(fires),
                'fires_queued': sent_count,
                'timestamp': datetime.now().isoformat()
            })
        }
        
    except Exception as e:
        print(f"❌ Error fetching fire data: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
        }

def get_secret(secret_name):
    """Retrieve secret from AWS Secrets Manager"""
    try:
        response = secretsmanager.get_secret_value(SecretId=secret_name)
        return json.loads(response['SecretString'])
    except Exception as e:
        print(f"Error retrieving secret: {str(e)}")
        return {}

def fetch_firms_data(map_key, source='VIIRS_SNPP_NRT', area='world', day_range=1):
    """
    Fetch fire data from NASA FIRMS API
    
    Args:
        map_key: NASA FIRMS API key
        source: Data source (VIIRS_SNPP_NRT, VIIRS_NOAA20_NRT, MODIS_NRT)
        area: Geographic area (world, USA, etc.)
        day_range: Number of days to fetch (1, 7, etc.)
    
    Returns:
        List of fire records
    """
    # NASA FIRMS API endpoint
    # Format: https://firms.modaps.eosdis.nasa.gov/api/area/csv/MAP_KEY/SOURCE/AREA/DAY_RANGE
    base_url = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
    url = f"{base_url}/{map_key}/{source}/{area}/{day_range}"
    
    print(f"📡 Fetching from: {url}")
    
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read().decode('utf-8')
            
            # Parse CSV data
            fires = parse_csv_data(data)
            print(f"📊 Parsed {len(fires)} fire records")
            
            return fires
            
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("ℹ️  No fire data available (404)")
            return []
        else:
            print(f"HTTP Error {e.code}: {e.reason}")
            raise
    except Exception as e:
        print(f"Error fetching FIRMS data: {str(e)}")
        raise

def parse_csv_data(csv_data):
    """
    Parse CSV fire data from FIRMS
    
    CSV Format:
    latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,
    instrument,confidence,version,bright_t31,frp,daynight
    """
    fires = []
    lines = csv_data.strip().split('\n')
    
    if len(lines) < 2:
        return fires
    
    # Parse header
    header = lines[0].split(',')
    
    # Parse data rows
    for line in lines[1:]:
        values = line.split(',')
        if len(values) < len(header):
            continue
        
        try:
            fire = dict(zip(header, values))
            
            # Extract key fields
            fire_record = {
                'latitude': float(fire.get('latitude', 0)),
                'longitude': float(fire.get('longitude', 0)),
                'brightness': float(fire.get('brightness', 0)),
                'confidence': fire.get('confidence', 'unknown'),
                'frp': float(fire.get('frp', 0)),  # Fire Radiative Power
                'acq_date': fire.get('acq_date', ''),
                'acq_time': fire.get('acq_time', ''),
                'satellite': fire.get('satellite', ''),
                'instrument': fire.get('instrument', ''),
                'daynight': fire.get('daynight', ''),
            }
            
            fires.append(fire_record)
            
        except (ValueError, KeyError) as e:
            print(f"Error parsing fire record: {str(e)}")
            continue
    
    return fires

def send_to_queue(fires, batch_size=10):
    """
    Send fire records to SQS queue in batches
    
    Args:
        fires: List of fire records
        batch_size: Number of records per SQS message (max 10)
    
    Returns:
        Number of fires successfully queued
    """
    sent_count = 0
    
    # Split fires into batches
    for i in range(0, len(fires), batch_size):
        batch = fires[i:i + batch_size]
        
        try:
            # Send batch to SQS
            message = {
                'fires': batch,
                'batch_id': f"batch_{i//batch_size}",
                'timestamp': datetime.now().isoformat()
            }
            
            response = sqs.send_message(
                QueueUrl=QUEUE_URL,
                MessageBody=json.dumps(message),
                MessageAttributes={
                    'batch_size': {
                        'StringValue': str(len(batch)),
                        'DataType': 'Number'
                    }
                }
            )
            
            sent_count += len(batch)
            print(f"✉️  Sent batch {i//batch_size}: {len(batch)} fires (MessageId: {response['MessageId']})")
            
        except Exception as e:
            print(f"Error sending batch to queue: {str(e)}")
            continue
    
    return sent_count

