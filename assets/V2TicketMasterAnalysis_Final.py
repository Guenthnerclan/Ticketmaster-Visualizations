import pandas as pd
import numpy as np
import logging
import io
import boto3
import time
import urllib
import re
import s3fs
import folium
from folium.plugins import MarkerCluster
import matplotlib.pyplot as plt
import seaborn as sns
from io import BytesIO
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from awsglue.utils import getResolvedOptions
import sys
from dython.nominal import associations

s3 = boto3.client('s3')
job_args =getResolvedOptions(sys.argv,["my_bucket"])
bucket= job_args["my_bucket"]

source=f"s3://{bucket}/combined_data.parquet"
df= pd.read_parquet(source)
pd.set_option('display.max_columns', None)

#### map
unique_df = df.drop_duplicates(subset=['date', 'time', 'name', 'venue'])
unique_df.replace('N/A', np.nan, inplace=True)
unique_df = unique_df.dropna()
unique_df['latitude'] = unique_df['latitude'].astype(float)
unique_df['longitude']=unique_df['longitude'].astype(float)

US_COORDINATES = (37.0902, -95.7129)
map_us = folium.Map(location=US_COORDINATES, zoom_start=5, tiles="cartodb positron")

# Create a MarkerCluster object
marker_cluster = MarkerCluster().add_to(map_us)

# Assuming 'df' is your DataFrame
for index, row in unique_df.iterrows():
    popup_text = f"{row['name']}, Date: {row['date']}, Time: {row['time']}"
    folium.CircleMarker(
        location=(row['latitude'], row['longitude']),
        radius=5,
        fill=True,
        fill_opacity=0.7,
        popup=folium.Popup(popup_text, parse_html=True)
    ).add_to(marker_cluster)  # Add to the marker cluster instead of directly to the map


temp_map_path = '/tmp/temp_map.html'
map_us.save(temp_map_path)

# Upload the temporary file to S3
s3_file_key = 'your_map.html'

# Using upload_file which is meant for file paths
s3.upload_file(temp_map_path, bucket, s3_file_key)


df['date_pulled'] = pd.to_datetime(df['date_pulled'])
df['date']=pd.to_datetime(df['date'])

df['Days_Till_Event'] = (df['date'] - df['date_pulled']).dt.days

df1 =df.drop(['time','genre','venue','city','state','max_price','latitude','longitude','date_pulled'], axis=1)

#events for next friday
friday_df = df1[df1['date'] == '2024-03-15']
print(friday_df['Days_Till_Event'].value_counts())
pivot_df = friday_df.pivot_table(index='name', columns='Days_Till_Event', values='min_price', aggfunc='first')

pivot_df.reset_index(inplace=True)

pivot_df.columns = ['Event'] + [f'{days}' for days in sorted(pivot_df.columns[1:])]
pivot_df.columns = [int(col) if col.isdigit() else col for col in pivot_df.columns]

plt.figure(figsize=(10, 10))

for index, row in pivot_df.iterrows():
    plt.plot([f'{days}' for days in sorted(row.index[1:])], row[1:], label=row['Event'])

plt.xlabel('# Days Before Event')
plt.ylabel('Minimum Price ($)')
plt.title('Price Change as Event Approaches')
plt.xticks(rotation=0)
plt.grid(True)
plt.gca().invert_xaxis()

plot_buffer = BytesIO()
plt.savefig(plot_buffer, format='png')
plot_buffer.seek(0)
s3.upload_fileobj(plot_buffer,bucket, 'images/price_change.png')


# After uploading, you can safely close the plot and buffer
plt.close()
plot_buffer.close()


df = df.dropna()

df['date'] = pd.to_datetime(df['date'])
df['day'] = df['date'].dt.day_name()

#max price by day of week------------------------
days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
df['day'] = pd.Categorical(df['day'], categories=days_order, ordered=True)

# Calculate the average max price by day of week
average_max_price_by_day = df.groupby('day')['max_price'].mean().reset_index()

# Plotting
plt.figure(figsize=(10, 8))  # Set the figure size (optional)
plt.plot(average_max_price_by_day['day'], average_max_price_by_day['max_price'], linestyle='-')
plt.title('Average Maximum Price by Day of the Week', fontsize=18)
plt.xlabel('Day of the Week', fontsize=15)
plt.ylabel('Average Max Price', fontsize=15)
plt.xticks(rotation=45, fontsize=12)


plot_buffer = BytesIO()
plt.savefig(plot_buffer, format='png')
plot_buffer.seek(0)
s3.upload_fileobj(plot_buffer,bucket, 'images/max_price_by_day.png')


# After uploading, you can safely close the plot and buffer
plt.close()
plot_buffer.close()

# min price by day of week -----------------------------
average_min_price_by_day = df.groupby('day')['min_price'].mean().reset_index()

# Plotting
plt.figure(figsize=(10, 8))  # Set the figure size (optional)
plt.plot(average_min_price_by_day['day'], average_min_price_by_day['min_price'])
plt.title('Average Minimum Price by Day of the Week', fontsize=18)
plt.xlabel('Day of the Week', fontsize=15)
plt.ylabel('Average Min Price', fontsize=15)
plt.xticks(rotation=45, fontsize=12)

plot_buffer = BytesIO()
plt.savefig(plot_buffer, format='png')
plot_buffer.seek(0)
s3.upload_fileobj(plot_buffer,bucket, 'images/min_price_by_day.png')


# After uploading, you can safely close the plot and buffer
plt.close()
plot_buffer.close()


# most popular venues ---------------------------
unique_df = df.drop_duplicates(subset=['date', 'time', 'name', 'venue'])
venues = unique_df.groupby('venue')['name'].count().reset_index()
venues = venues.sort_values(by='name', ascending=False)
venues = venues.head(10)


plt.figure(figsize=(16, 8))  # Set the figure size (optional)
plt.barh(venues['venue'], venues['name'])  # Use barh instead of bar for horizontal bars
plt.title('Most Popular Rock Venues', fontsize=22)
plt.xlabel('Number of Concerts', fontsize=18)  # This label now applies to the x-axis
plt.ylabel('Venue', fontsize=18)  # This label now applies to the y-axis
plt.xticks(fontsize=14)  # Adjust font size as needed
plt.yticks(fontsize=14)  # Make sure the y-ticks (venue names) are readable
plt.tight_layout()


plot_buffer = BytesIO()
plt.savefig(plot_buffer, format='png')
plot_buffer.seek(0)
s3.upload_fileobj(plot_buffer,bucket, 'images/popular_venue.png')


# After uploading, you can safely close the plot and buffer
plt.close()
plot_buffer.close()


#most expensive venues --------------------------


venues = df.groupby('venue')['max_price'].median().reset_index()
venues = venues.sort_values(by='max_price', ascending=False)
venues = venues.head(10)

plt.figure(figsize=(16, 8))  # Set the figure size (optional)
plt.barh(venues['venue'], venues['max_price'])  # Use barh instead of bar for horizontal bars
plt.title('Most Expensive Rock Venues', fontsize=22)
plt.xlabel('Median Max Price', fontsize=18)  # This label now applies to the x-axis
plt.ylabel('Venue', fontsize=18)  # This label now applies to the y-axis
plt.xticks(fontsize=14)  # Adjust font size as needed
plt.yticks(fontsize=14)  # Make sure the y-ticks (venue names) are readable
plt.tight_layout()

plot_buffer = BytesIO()
plt.savefig(plot_buffer, format='png')
plot_buffer.seek(0)
s3.upload_fileobj(plot_buffer,bucket, 'images/expensive_venue.png')


# After uploading, you can safely close the plot and buffer
plt.close()
plot_buffer.close()



# max price over time -----------------------
full_data = df.replace({'N/A': np.nan})


full_data['latitude'] = full_data['latitude'].astype(float)
full_data['longitude'] = full_data['longitude'].astype(float)

mean_prices = full_data.groupby('date')['max_price'].mean()

# Plot the line plot
plt.figure(figsize=(10, 6))
plt.plot(mean_prices.index, mean_prices.values, marker='o', color='b', linestyle='-')

# Set labels and title
plt.xlabel('')
plt.ylabel('Mean Price')
plt.title('Max Price over time')

# Rotate x-axis labels
plt.xticks(rotation=45, ha='right')
plt.tight_layout()

plot_buffer = BytesIO()
plt.savefig(plot_buffer, format='png')
plot_buffer.seek(0)
s3.upload_fileobj(plot_buffer,bucket, 'images/max_over_time.png')


# After uploading, you can safely close the plot and buffer
plt.close()
plot_buffer.close()

#DIFF BETWEEN EVENT day PRICE AND dayS AHEAD PRICE -----------------
curr_events = full_data[full_data['Days_Till_Event'] == 0]
merged = pd.merge(curr_events,full_data,on=['name','city','state','day','genre','date','venue','latitude','longitude']).drop(columns=['Days_Till_Event_x','genre','time_y','date_pulled_y'])
merged.columns = ['name','date','time','venue','city','state','min_price_dayof','max_price_dayof','latitude','longitude','date_pulled','day','min_price_other','max_price_other','Days_Till_Event']

merged['min_price_diff_rel'] = (-merged['min_price_dayof'] + merged['min_price_other'])/merged['min_price_dayof']
merged['max_price_diff_rel'] = (-merged['max_price_dayof'] + merged['max_price_other'])/merged['max_price_dayof']

# Create the scatter plot
plt.figure(figsize=(8, 6))
plt.scatter(merged['Days_Till_Event'], merged['min_price_diff_rel'], color='blue', alpha=0.5)  # alpha sets transparency
plt.xlabel('days until the event')
plt.ylabel('Price diff ($)')
plt.title('Min Event day price - future day price')

# Show plot
plt.tight_layout()
plt.show()

plot_buffer = BytesIO()
plt.savefig(plot_buffer, format='png')
plot_buffer.seek(0)
s3.upload_fileobj(plot_buffer,bucket, 'images/min_diff_event_day.png')


# After uploading, you can safely close the plot and buffer
plt.close()
plot_buffer.close()


# Create the scatter plot
plt.figure(figsize=(8, 6))
plt.scatter(merged['Days_Till_Event'], merged['max_price_diff_rel'], color='blue', alpha=0.5)  # alpha sets transparency
plt.xlabel('days until the event')
plt.ylabel('Price diff ($)')
plt.title('Max Event day price - future day price')

# Show plot
plt.tight_layout()

plot_buffer = BytesIO()
plt.savefig(plot_buffer, format='png')
plot_buffer.seek(0)
s3.upload_fileobj(plot_buffer,bucket, 'images/max_diff_event_day.png')


# After uploading, you can safely close the plot and buffer
plt.close()
plot_buffer.close()


#max price city -------
unique_events_df = full_data.drop(columns=['date_pulled','Days_Till_Event']).drop_duplicates()
cities = unique_events_df[['city','min_price','max_price']].groupby(by='city').agg(["median","mean","std","count"])
cities = cities.reset_index()
cities.columns = ['city','min_price_median','min_price_mean','min_price_std','counta','max_price_median','max_price_mean','max_price_std','count']
cities = cities.drop(columns=['counta'])

sorted_df = cities.sort_values(['max_price_mean'],ascending=False)[0:20]

# Extract the sorted data
x = sorted_df['city']
y = sorted_df['max_price_mean']

# Create the bar plot
plt.figure(figsize=(8, 6))
plt.barh(x,y, color='skyblue')
plt.xlabel('Max Price')
plt.ylabel('City')
plt.title('Max price by City sorted max price')

# Show plot
plt.gca().invert_yaxis()  # Invert y-axis to have the highest bar on the left
plt.tight_layout()
plt.show()

plot_buffer = BytesIO()
plt.savefig(plot_buffer, format='png')
plot_buffer.seek(0)
s3.upload_fileobj(plot_buffer,bucket, 'images/max_city.png')
plt.close()
plot_buffer.close()

#CORRELATION MATRIX BETWEEN PRICE AND OTHER VARIABLES


complete_correlation = associations(full_data[['venue','city','state','min_price','max_price','day','Days_Till_Event']], filename= 'complete_correlation.png', figsize=(10,10),hide_rows=['city','state','day','Days_Till_Event','venue'])
df_complete_corr=complete_correlation['corr']
df_complete_corr.dropna(axis=1, how='all').dropna(axis=0, how='all').style.background_gradient(cmap='coolwarm', axis=None)#.set_precision(2)
# Plot heatmap
plt.figure(figsize=(10, 10))
plt.imshow(df_complete_corr, cmap='coolwarm', interpolation='nearest')
plt.colorbar()

# Annotate each cell with the corresponding value
for i in range(len(df_complete_corr.index)):
    for j in range(len(df_complete_corr.columns)):
        plt.text(j, i, '{:.2f}'.format(df_complete_corr.iloc[i, j]), ha='center', va='center', color='black')

plt.xticks(range(len(df_complete_corr.columns)), df_complete_corr.columns, rotation=45)
plt.yticks(range(len(df_complete_corr.index)), df_complete_corr.index)

plot_buffer = BytesIO()
plt.savefig(plot_buffer, format='png')
plot_buffer.seek(0)
s3.upload_fileobj(plot_buffer,bucket, 'images/complete_correlation.png')
plt.close()
plot_buffer.close()


#VENUE PLOTS

venues = unique_events_df[['venue','min_price','max_price']].groupby(by='venue').agg(["median","mean","std","count"])
venues = venues.reset_index()
venues.columns = ['venue','min_price_median','min_price_mean','min_price_std','counta','max_price_median','max_price_mean','max_price_std','count']
venues = venues.drop(columns=['counta'])

venue_top10_max = pd.merge(venues[venues['count'] >= 5].sort_values(by='max_price_median',ascending=False)[0:10],unique_events_df,on=['venue'])

#HIGHEST MEDIAN PRICE VENUE BOX PLOTS, AT LEAST 5 EVENTS AT VENUE
import matplotlib.pyplot as plt
import seaborn as sns

# Create the boxplot
plt.figure(figsize=(10, 6))
sns.boxplot(x='venue', y='max_price', data=venue_top10_max, palette='Set3')

# Set labels and title
plt.ylabel('Max Price')
plt.title('Max price of top 10 highest venues')

# Rotate x-axis labels
plt.xticks(rotation=45, ha='right')

# Show plot
plt.tight_layout()

plot_buffer = BytesIO()
plt.savefig(plot_buffer, format='png')
plot_buffer.seek(0)
s3.upload_fileobj(plot_buffer,bucket, 'images/high_median_venue.png')
plt.close()
plot_buffer.close()

