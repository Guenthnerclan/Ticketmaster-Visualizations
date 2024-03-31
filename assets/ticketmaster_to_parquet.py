import boto3
from botocore.exceptions import ClientError
import requests
import numpy as np
import json
import pandas as pd
import sys
from datetime import datetime, timedelta

# This cannot import locally, only for Glue Environment:
from awsglue.utils import getResolvedOptions

# Get bucket argument from stack file
job_args = getResolvedOptions(sys.argv, ["my_bucket"])

# Fetch Ticketmaster API key
def get_secret():

    secret_name = "finalproject/daniel/ticketmaster"
    region_name = "us-west-2"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:

        raise e

    secret = get_secret_value_response['SecretString']
    parsed_json = json.loads(secret)
    api_key = parsed_json["TICKETMASTER_API_KEY"]

    return api_key

api_key = get_secret()

print("Running...")

# Inititalize boto3 client for S3
s3 = boto3.client("s3")

# Define params for request to ticketmaster
base_url = 'https://app.ticketmaster.com/discovery/v2/events.json?'
country_code = 'US'
classificationName = 'Rock'
page_size = 200
start_date = datetime.now()
end_date = start_date + timedelta(days=300)

# Initialize empty list
all_events = []

# Loop through all days
for single_date in (start_date + timedelta(n) for n in range((end_date - start_date).days)):
    
    # Format date
    formatted_date = single_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    next_day = (single_date + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Start at page 0
    current_page = 0
    total_pages = None

    # Go until page limit is hit
    while total_pages is None or current_page < total_pages:

        # Hit ticketmaster API
        url = f'{base_url}countryCode={country_code}&apikey={api_key}&size={page_size}&page={current_page}&startDateTime={formatted_date}&endDateTime={next_day}&classificationName={classificationName}'
        response = requests.get(url)
        
        # Make sure response code is good, if not, just exit the loop
        if response.status_code == 200:

            # Get data
            data = response.json()
            events = data.get('_embedded', {}).get('events', [])
            
            # Loop through events and extract information
            for event in events:
                min_price = None
                max_price = None
                
                price_ranges = event.get('priceRanges', [])
                if price_ranges:
                    min_price = price_ranges[0].get('min')
                    max_price = price_ranges[0].get('max')

                all_events.append({
                    'name': event['name'],
                    'date': event['dates']['start'].get('localDate'),
                    'time': event['dates']['start'].get('localTime'),
                    'genre': classificationName,
                    'venue': event.get('_embedded', {}).get('venues', [{}])[0].get('name', 'N/A'),
                    'city': event.get('_embedded', {}).get('venues', [{}])[0].get('city', {}).get('name', 'N/A'),
                    'state': event.get('_embedded', {}).get('venues', [{}])[0].get('state', {}).get('name', 'N/A'),
                    'min_price': min_price,
                    'max_price': max_price,
                    'latitude': event.get('_embedded', {}).get('venues', [{}])[0].get('location', {}).get('latitude', 'N/A'),
                    'longitude': event.get('_embedded', {}).get('venues', [{}])[0].get('location', {}).get('longitude', 'N/A'),
                    'date_pulled': start_date.strftime('%m/%d/%Y')
                })
            
            if total_pages is None:
                total_pages = data['page']['totalPages']
            current_page += 1
        else:
            print(f'Error fetching events for {formatted_date}:', response.status_code)
            break

df = pd.DataFrame(all_events)

#get rid of erro on nans when converting to paquet
df['min_price'] = pd.to_numeric(df['min_price'], errors='coerce')
df['max_price'] = pd.to_numeric(df['max_price'], errors='coerce')

df.to_parquet(f"s3://{job_args['my_bucket']}/ticketmaster_new.parquet", index=False)

# df.to_parquet('rock_data_3-6.parquet')
# print("Created rock_data_3-6.parquet")