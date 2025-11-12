"""
Lambda function to process DynamoDB Streams
Monitors changes to the fire data table and sends notifications
"""
import json
import boto3
from datetime import datetime
import os

# Initialize AWS services
sns = boto3.client('sns')

SNS_TOPIC_ARN = os.environ['SNS_TOPIC_ARN']

def lambda_handler(event, context):
    """
    Process DynamoDB Stream events
    Triggered when new fires are added to the table
    
    Event format:
    {
        "Records": [
            {
                "eventName": "INSERT" | "MODIFY" | "REMOVE",
                "dynamodb": {
                    "NewImage": {...},
                    "OldImage": {...}
                }
            }
        ]
    }
    """
    try:
        print(f"📊 Processing {len(event['Records'])} DynamoDB stream records")
        
        new_fires = []
        updated_fires = []
        removed_fires = []
        
        # Process each stream record
        for record in event['Records']:
            event_name = record['eventName']
            
            if event_name == 'INSERT':
                fire = parse_dynamodb_item(record['dynamodb']['NewImage'])
                new_fires.append(fire)
                
            elif event_name == 'MODIFY':
                fire = parse_dynamodb_item(record['dynamodb']['NewImage'])
                updated_fires.append(fire)
                
            elif event_name == 'REMOVE':
                fire = parse_dynamodb_item(record['dynamodb']['OldImage'])
                removed_fires.append(fire)
        
        # Send notifications for new fires
        if new_fires:
            send_fire_alerts(new_fires)
        
        # Log statistics
        print(f"✅ Stream processing complete:")
        print(f"   - New fires: {len(new_fires)}")
        print(f"   - Updated fires: {len(updated_fires)}")
        print(f"   - Removed fires: {len(removed_fires)}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Stream processing complete',
                'new_fires': len(new_fires),
                'updated_fires': len(updated_fires),
                'removed_fires': len(removed_fires),
                'timestamp': datetime.now().isoformat()
            })
        }
        
    except Exception as e:
        print(f"❌ Error processing stream: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
        }

def parse_dynamodb_item(dynamodb_item):
    """
    Parse DynamoDB item from stream record
    
    Args:
        dynamodb_item: DynamoDB item in stream format
    
    Returns:
        dict: Parsed fire record
    """
    try:
        fire = {
            'fire_id': dynamodb_item.get('fire_id', {}).get('S', ''),
            'latitude': float(dynamodb_item.get('latitude', {}).get('N', 0)),
            'longitude': float(dynamodb_item.get('longitude', {}).get('N', 0)),
            'brightness': float(dynamodb_item.get('brightness', {}).get('N', 0)),
            'confidence': dynamodb_item.get('confidence', {}).get('S', 'unknown'),
            'frp': float(dynamodb_item.get('frp', {}).get('N', 0)),
            'location_city': dynamodb_item.get('location_city', {}).get('S', 'Unknown'),
            'location_state': dynamodb_item.get('location_state', {}).get('S', 'Unknown'),
            'location_country': dynamodb_item.get('location_country', {}).get('S', 'Unknown'),
            'satellite': dynamodb_item.get('satellite', {}).get('S', ''),
            'acq_date': dynamodb_item.get('acq_date', {}).get('S', ''),
            'acq_time': dynamodb_item.get('acq_time', {}).get('S', ''),
        }
        return fire
    except Exception as e:
        print(f"Error parsing DynamoDB item: {str(e)}")
        return {}

def send_fire_alerts(fires):
    """
    Send SNS notifications for new fires
    
    Args:
        fires: List of new fire records
    """
    try:
        # Group fires by country for better notification organization
        fires_by_country = {}
        for fire in fires:
            country = fire.get('location_country', 'Unknown')
            if country not in fires_by_country:
                fires_by_country[country] = []
            fires_by_country[country].append(fire)
        
        # Create notification message
        total_fires = len(fires)
        countries = list(fires_by_country.keys())
        
        # Build summary message
        subject = f"🔥 Firewatch Alert: {total_fires} New Fire(s) Detected"
        
        message_lines = [
            f"Firewatch has detected {total_fires} new active fire(s).",
            f"",
            f"Summary by Country:",
            f"─────────────────────"
        ]
        
        # Add country breakdown
        for country, country_fires in sorted(fires_by_country.items()):
            message_lines.append(f"")
            message_lines.append(f"📍 {country}: {len(country_fires)} fire(s)")
            
            # Add details for first 5 fires per country
            for i, fire in enumerate(country_fires[:5]):
                location = f"{fire.get('location_city', 'Unknown')}, {fire.get('location_state', 'Unknown')}"
                coords = f"({fire.get('latitude', 0):.4f}, {fire.get('longitude', 0):.4f})"
                confidence = fire.get('confidence', 'unknown')
                frp = fire.get('frp', 0)
                
                message_lines.append(
                    f"  • {location} {coords}"
                )
                message_lines.append(
                    f"    Confidence: {confidence}, FRP: {frp:.1f} MW"
                )
            
            if len(country_fires) > 5:
                message_lines.append(f"  ... and {len(country_fires) - 5} more")
        
        # Add footer
        message_lines.extend([
            f"",
            f"─────────────────────",
            f"Detection time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"",
            f"This is an automated alert from Firewatch.",
        ])
        
        message = "\n".join(message_lines)
        
        # Send to SNS
        response = sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message,
            MessageAttributes={
                'fire_count': {
                    'DataType': 'Number',
                    'StringValue': str(total_fires)
                },
                'countries': {
                    'DataType': 'String.Array',
                    'StringValue': json.dumps(countries)
                }
            }
        )
        
        print(f"📧 Sent SNS notification: {response['MessageId']}")
        print(f"   Subject: {subject}")
        
    except Exception as e:
        print(f"❌ Error sending fire alerts: {str(e)}")
        raise

def format_fire_location(fire):
    """Format fire location for display"""
    city = fire.get('location_city', 'Unknown')
    state = fire.get('location_state', 'Unknown')
    country = fire.get('location_country', 'Unknown')
    
    parts = []
    if city != 'Unknown':
        parts.append(city)
    if state != 'Unknown':
        parts.append(state)
    if country != 'Unknown':
        parts.append(country)
    
    return ', '.join(parts) if parts else 'Unknown Location'

