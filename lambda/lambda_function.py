import json
import urllib.request
import urllib.parse
from datetime import datetime
import boto3
from decimal import Decimal
import os

# Initialize AWS services
dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('DYNAMODB_TABLE_NAME', 'firewatch-data')
table = dynamodb.Table(table_name)

# BigDataCloud API Key from environment variable
BIGDATACLOUD_API_KEY = os.environ.get('BIGDATACLOUD_API_KEY')

def lambda_handler(event, context):
    """
    Process fire coordinates and enrich with location data from BigDataCloud
    """
    try:
        fires = event.get('fires', [])
        
        if not fires:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'No fire data provided'
                })
            }
        
        stored_count = 0
        results = []
        
        for fire in fires:
            try:
                if 'latitude' not in fire or 'longitude' not in fire:
                    continue
                
                location_data = get_location_from_coordinates(
                    fire['latitude'], 
                    fire['longitude']
                )
                
                fire_record = {
                    'latitude': fire['latitude'],
                    'longitude': fire['longitude'],
                    'brightness': fire.get('brightness', 0),
                    'confidence': fire.get('confidence', 'unknown'),
                    'frp': fire.get('frp', 0),
                    'location_city': location_data.get('city', 'Unknown'),
                    'location_locality': location_data.get('locality', 'Unknown'),
                    'location_country': location_data.get('countryName', 'Unknown'),
                    'location_state': location_data.get('principalSubdivision', 'Unknown'),
                }
                
                store_fire_data(fire_record)
                stored_count += 1
                
                results.append({
                    'coordinates': f"{fire['latitude']}, {fire['longitude']}",
                    'location': f"{fire_record['location_city']}, {fire_record['location_state']}",
                    'status': 'success'
                })
                
            except Exception as e:
                print(f"Error processing fire: {str(e)}")
                continue
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Fire data processing complete',
                'stored_successfully': stored_count,
                'results': results
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def get_location_from_coordinates(latitude, longitude):
    base_url = 'https://api.bigdatacloud.net/data/reverse-geocode-client'
    params = {
        'latitude': latitude,
        'longitude': longitude,
        'localityLanguage': 'en',
        'key': BIGDATACLOUD_API_KEY
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    
    try:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Geocoding error: {str(e)}")
        return {
            'city': 'Unknown',
            'locality': 'Unknown',
            'countryName': 'Unknown',
            'principalSubdivision': 'Unknown'
        }

def store_fire_data(fire):
    timestamp = int(datetime.now().timestamp())
    fire_id = f"{fire['latitude']}_{fire['longitude']}_{timestamp}"
    
    item = {
        'fire_id': fire_id,
        'timestamp': timestamp,
        'latitude': Decimal(str(fire['latitude'])),
        'longitude': Decimal(str(fire['longitude'])),
        'brightness': Decimal(str(fire['brightness'])) if fire['brightness'] else Decimal('0'),
        'confidence': fire['confidence'],
        'frp': Decimal(str(fire['frp'])) if fire['frp'] else Decimal('0'),
        'location_city': fire.get('location_city', 'Unknown'),
        'location_locality': fire.get('location_locality', 'Unknown'),
        'location_state': fire.get('location_state', 'Unknown'),
        'location_country': fire.get('location_country', 'Unknown'),
        'created_at': datetime.now().isoformat()
    }
    
    table.put_item(Item=item)
    print(f"✅ Stored: {fire_id}")