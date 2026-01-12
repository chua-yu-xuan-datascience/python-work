import boto3
import requests
import json
from bs4 import BeautifulSoup
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
from datetime import datetime, timedelta
import re
import pandas as pd
import time

# Function to upload a file to an S3 bucket
def upload_to_s3(file_name, bucket_name, object_name=None):
    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = file_name

    # Initialize a session using Amazon S3
    s3_client = boto3.client('s3')

    try:
        # Upload the file to S3
        s3_client.upload_file(file_name, bucket_name, object_name)
        print(f"File {file_name} uploaded to {bucket_name} as {object_name}.")
    except FileNotFoundError:
        print(f"The file {file_name} was not found.")
    except NoCredentialsError:
        print("Credentials not available.")
    except PartialCredentialsError:
        print("Incomplete credentials provided.")

# Helper functions 

def convert_event_time(event_time):
    
    # Convert the datetime object to the desired format
    formatted_time = event_time.strftime("%Y-%m-%d-%H")
    
    return formatted_time

def posted_date(current_time,ago):
    
    if ago.lower() == "just now":
        delta = timedelta(days=0)

    elif ago.split(" ago")[0][-1] == "m":
        mins = int(ago.split(" ago")[0][:-1])
        delta = timedelta(minutes=mins)

    elif ago.split(" ago")[0][-1] == "h":
        hrs = int(ago.split(" ago")[0][:-1])
        delta = timedelta(hours=hrs) 

    elif ago.split(" ago")[0][-1] == "d":
        day = int(ago.split(" ago")[0][:-1])
        delta = timedelta(days=day)
        
    posted_date = current_time - delta
    
    formatted = posted_date.strftime("%Y-%m-%d")
    
    return formatted

def posted_hour(current_time,ago):
    
    if ago.lower() == "just now":
        delta = timedelta(days=0)

    elif ago.split(" ago")[0][-1] == "m":
        mins = int(ago.split(" ago")[0][:-1])
        delta = timedelta(minutes=mins)

    elif ago.split(" ago")[0][-1] == "h":
        hrs = int(ago.split(" ago")[0][:-1])
        delta = timedelta(hours=hrs) 
    
    elif ago.split(" ago")[0][-1] == "d":
        return None
    
    posted_date = current_time - delta
    
    hour = (posted_date.hour)
    
    return hour

# Function to scrape data from a webpage and save to a JSON file
def scrape_jobs(output_file):

    jobs_list = []
    
    ended = False

    for page in range(1,400):

        url = fr"https://www.jobstreet.com.sg/jobs?daterange=2&page={page}&sortmode=ListedDate"
        response = requests.get(url)

        if response.status_code == 200:
            
            print(f"Page {page} loaded succesfully.")

            soup = BeautifulSoup(response.content, 'html.parser')
            
            
            pattern1 = re.compile(r'No matching search results')
            nomore = soup.find(string=pattern1)
            
            if nomore != None:
                print("All results from past 2 days scraped.")
                break
            
            # Get the current date and time
            current_datetime = datetime.now() + timedelta(hours=8) 

            articles = soup.find_all(attrs={"data-testid": "job-card"})

            for article in articles:

                job_title = article.find(attrs={"data-automation": "jobTitle"}).text
                
                try:
                    company = article.find(attrs={"data-automation": "jobCompany"})
                    company_name = company.text
                    adv_url = company['href']
                    if '61941084' in adv_url:
                        category = "MCF"
                    else:
                        category = "OK"
                except:
                    company_name = "Private Advertiser"
                    adv_url = "PRIVATE"
                    category = "PRIVATE"
                
                job_location_elements = article.find_all(attrs={"data-automation": "jobLocation"})
                job_locations = [location.text for location in job_location_elements]

                pattern = re.compile(r'This is a .*? job')
                matching_text = article.find(string=pattern)

                job_type = matching_text.split()[3]

                if job_type == "Full" or job_type == "Part":
                    job_type = f"{job_type} Time"

                if len(job_locations) == 1:
                    job_region = job_locations[0]
                    job_location_specific = ""

                else:
                    job_location_specific = job_locations[0]
                    job_region = job_locations[1]

                try:
                    job_salary = article.find(attrs={"data-automation": "jobSalary"}).text
                except:
                    job_salary = ""

                ago = article.find(attrs={"data-automation": "jobListingDate"}).text
                
                if ago.split(" ago")[0][-1] == "d":
                    ended = True
                    break

                job_listing_date = posted_date(current_datetime, ago)

                job_hour = posted_hour(current_datetime, ago)

                job_classification = article.find(attrs={"data-automation": "jobClassification"}).text
                job_classification = job_classification.replace("(", "").replace(")", "")
                job_sub_classification = article.find(attrs={"data-automation": "jobSubClassification"}).text

                job_element = article.find(attrs={"data-automation": "jobTitle"})
                path = job_element['href']
                path = path.split('/')[2]
                job_id = path.split('?')[0]
                job_url = fr"https://www.jobstreet.com.sg/job/{job_id}"

                job_details = {}
                job_details["job_title"] = job_title
                job_details["job_id"] = job_id
                job_details["job_url"] = job_url
                job_details["job_cat"] = category
                job_details["adv_url"] = adv_url
                job_details["company"] = company_name
                job_details["job_type"] = job_type
                job_details["job_region"] = job_region
                job_details["job_location_specific"] = job_location_specific
                job_details["job_salary"] = job_salary
                job_details["job_date"] = job_listing_date
                job_details["job_hour"] = job_hour
                job_details["job_classification"] = job_classification
                job_details["job_sub_classification"] = job_sub_classification

                jobs_list.append(job_details)
                
            if ended == True:
                print("All jobs from the past 24 hours scraped.")
                break
            
            time.sleep(1)
            
        else:
            print(f"Page blocked by JobStreet.")
            break
        
    df = pd.DataFrame(jobs_list)

    # Save the scraped data to a JSON file
    df.to_json(output_file, orient='records', lines=True)
    
    return output_file

def lambda_handler(event, context):
    
    label = convert_event_time(datetime.now() + timedelta(hours=8))
    
    output_file = f"/tmp/jobs-{label}.json"
    bucket_name = 'testing-bucket-6969'
    object_name = f'jobs-{label}.json'
    print("hello")
    file_name = scrape_jobs(output_file)
    upload_to_s3(file_name, bucket_name, object_name)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Script executed successfully and file uploaded to S3.')
    }