import pandas as pd
import numpy as np
import logging
import io
import boto3
import time
import urllib
import re
import s3fs
from io import BytesIO
from awsglue.utils import getResolvedOptions
import sys

# Initialize boto3 client
s3 = boto3.client('s3')

# Get job args from glue job
job_args = getResolvedOptions(sys.argv,["my_bucket"])
bucket= job_args["my_bucket"]

# Specify two files to join
source=f"s3://{bucket}/combined_data.parquet"
source2 =f"s3://{bucket}/ticketmaster_new.parquet"

# Read in parquet
df2 = pd.read_parquet(source2)

# If file doesn't exist, create it, otherwise, concat the two dataframes
try: 
    df= pd.read_parquet(source)
    combined_df = pd.concat([df, df2], ignore_index=True)

    print("Combined DataFrame:")
    # Print combined DataFrame

    print(combined_df)  

    # Dump combined dataframe into S3 bucket
    combined_df.to_parquet(source, index=False)
    print("DataFrame saved to Parquet file: combined_data.parquet")

except FileNotFoundError:

    df2.to_parquet(source, index=False)
