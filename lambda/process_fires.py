"""
Lambda function to process fire data from SQS
Enriches with location data and stores in DynamoDB
"""
import json
import urllib.request
import urllib.parse
from datetime import datetime
import boto3
from decimal import Decimal
import os

# Initialize AWS services
dynamodb = boto3.resource('dynamodb')
secretsmanager = boto3.client('secretsmanager')

TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
BIGDATA_SECRET_NAME = os.environ['BIGDATA_SECRET_NAME']

table = dynamodb.Table(TABLE_NAME)

# Cache for API key (loaded once per container lifecycle)
_api_key_cache = None

def lambda_handler(event, context):
    """
    Process fire records from SQS, enrich with location data, and store in DynamoDB
    
    Event format (from SQS):
    {
        "Records": [
            {
                "body": "{\"fires\": [...], \"batch_id\": \"...\", \"timestamp\": \"...\"}"
            }
        ]
    }
    """
    try:
        print(f"🔄 Processing {len(event['Records'])} SQS messages")
        
        total_processed = 0
        total_stored = 0
        errors = []
        
        # Process each SQS message
        for record in event['Records']:
            try:
                # Parse message body
                message = json.loads(record['body'])
                fires = message.get('fires', [])
                batch_id = message.get('batch_id', 'unknown')
                
                print(f"📦 Processing batch {batch_id} with {len(fires)} fires")
                
                # Process each fire in the batch
                for fire in fires:
                    try:
                        success = process_fire(fire)
                        if success:
                            total_stored += 1
                        total_processed += 1
                    except Exception as e:
                        print(f"⚠️  Error processing individual fire: {str(e)}")
                        errors.append({
                            'fire': fire,
                            'error': str(e)
                        })
                        continue
                
                print(f"✅ Batch {batch_id} complete: {total_stored} stored")
                
            except Exception as e:
                print(f"❌ Error processing SQS record: {str(e)}")
                errors.append({
                    'record': record['messageId'],
                    'error': str(e)
                })
                continue
        
        # Return summary
        return {
            'statusCode': 200 if not errors else 207,  # 207 = Partial success
            'body': json.dumps({
                'message': 'Processing complete',
                'processed': total_processed,
                'stored': total_stored,
                'errors': len(errors),
                'error_details': errors[:10] if errors else [],  # Limit error details
                'timestamp': datetime.now().isoformat()
            })
        }
        
    except Exception as e:
        print(f"❌ Critical error in handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
        }

def process_fire(fire):
    """
    Process a single fire record: geocode and store
    
    Args:
        fire: Fire record dictionary
    
    Returns:
        bool: True if stored successfully
    """
    try:
        # Validate required fields
        if 'latitude' not in fire or 'longitude' not in fire:
            print(f"⚠️  Skipping fire with missing coordinates")
            return False
        
        lat = fire['latitude']
        lon = fire['longitude']
        
        # Get location data from BigDataCloud
        location_data = get_location_from_coordinates(lat, lon)
        
        # Build fire record
        fire_record = {
            'latitude': lat,
            'longitude': lon,
            'brightness': fire.get('brightness', 0),
            'confidence': fire.get('confidence', 'unknown'),
            'frp': fire.get('frp', 0),
            'acq_date': fire.get('acq_date', ''),
            'acq_time': fire.get('acq_time', ''),
            'satellite': fire.get('satellite', ''),
            'instrument': fire.get('instrument', ''),
            'daynight': fire.get('daynight', ''),
            'location_city': location_data.get('city', 'Unknown'),
            'location_locality': location_data.get('locality', 'Unknown'),
            'location_country': location_data.get('countryName', 'Unknown'),
            'location_state': location_data.get('principalSubdivision', 'Unknown'),
        }
        
        # Store in DynamoDB
        store_fire_data(fire_record)
        
        return True
        
    except Exception as e:
        print(f"Error processing fire at ({fire.get('latitude')}, {fire.get('longitude')}): {str(e)}")
        raise

def get_location_from_coordinates(latitude, longitude):
    """
    Get location information from coordinates using BigDataCloud API
    
    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
    
    Returns:
        dict: Location data
    """
    global _api_key_cache
    
    # Load API key from cache or Secrets Manager
    if _api_key_cache is None:
        _api_key_cache = get_bigdata_api_key()
    
    base_url = 'https://api.bigdatacloud.net/data/reverse-geocode-client'
    params = {
        'latitude': latitude,
        'longitude': longitude,
        'localityLanguage': 'en',
    }
    
    # Add API key if available
    if _api_key_cache:
        params['key'] = _api_key_cache
    
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            location_data = json.loads(response.read().decode('utf-8'))
            return location_data
    except Exception as e:
        print(f"⚠️  Geocoding error for ({latitude}, {longitude}): {str(e)}")
        # Return default values on error
        return {
            'city': 'Unknown',
            'locality': 'Unknown',
            'countryName': 'Unknown',
            'principalSubdivision': 'Unknown'
        }

def get_bigdata_api_key():
    """Get BigDataCloud API key from Secrets Manager"""
    try:
        response = secretsmanager.get_secret_value(SecretId=BIGDATA_SECRET_NAME)
        secret = json.loads(response['SecretString'])
        return secret.get('api_key', '')
    except Exception as e:
        print(f"⚠️  Could not load BigDataCloud API key: {str(e)}")
        return ''

def store_fire_data(fire):
    """
    Store fire data in DynamoDB with deduplication
    
    Args:
        fire: Fire record dictionary
    """
    timestamp = int(datetime.now().timestamp())
    
    # Create unique fire_id based on coordinates and acquisition date/time
    # This helps avoid duplicates from overlapping API calls
    acq_datetime = f"{fire.get('acq_date', '')}_{fire.get('acq_time', '')}"
    if acq_datetime == "_":
        # Fallback to current timestamp if no acquisition time
        fire_id = f"{fire['latitude']}_{fire['longitude']}_{timestamp}"
    else:
        fire_id = f"{fire['latitude']}_{fire['longitude']}_{acq_datetime}"
    
    # Build DynamoDB item
    item = {
        'fire_id': fire_id,
        'timestamp': timestamp,
        'latitude': Decimal(str(fire['latitude'])),
        'longitude': Decimal(str(fire['longitude'])),
        'brightness': Decimal(str(fire['brightness'])) if fire['brightness'] else Decimal('0'),
        'confidence': fire['confidence'],
        'frp': Decimal(str(fire['frp'])) if fire['frp'] else Decimal('0'),
        'acq_date': fire.get('acq_date', ''),
        'acq_time': fire.get('acq_time', ''),
        'satellite': fire.get('satellite', ''),
        'instrument': fire.get('instrument', ''),
        'daynight': fire.get('daynight', ''),
        'location_city': fire.get('location_city', 'Unknown'),
        'location_locality': fire.get('location_locality', 'Unknown'),
        'location_state': fire.get('location_state', 'Unknown'),
        'location_country': fire.get('location_country', 'Unknown'),
        'created_at': datetime.now().isoformat()
    }
    
    try:
        # Use put_item with condition to prevent overwriting existing records
        table.put_item(
            Item=item,
            ConditionExpression='attribute_not_exists(fire_id)'
        )
        print(f"✅ Stored: {fire_id} ({item['location_city']}, {item['location_state']})")
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        print(f"ℹ️  Duplicate fire_id {fire_id}, skipping")
    except Exception as e:
        print(f"❌ Error storing fire {fire_id}: {str(e)}")
        raise

