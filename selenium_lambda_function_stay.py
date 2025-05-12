import json
import boto3
import time
import random
import re
import pandas as pd
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from botocore.exceptions import NoCredentialsError, PartialCredentialsError

# Upload file to S3
def upload_to_s3(file_name, bucket_name, object_name=None):
    if object_name is None:
        object_name = file_name
    s3_client = boto3.client('s3')
    try:
        s3_client.upload_file(file_name, bucket_name, object_name)
        print(f"Uploaded {file_name} to {bucket_name}/{object_name}")
    except FileNotFoundError:
        print(f"{file_name} not found.")
    except NoCredentialsError:
        print("AWS credentials missing.")
    except PartialCredentialsError:
        print("Incomplete credentials.")

# Date helpers
def convert_event_time(event_time):
    return event_time.strftime("%Y-%m-%d-%H")

def posted_date(current_time, ago):
    if ago.lower() == "just now":
        delta = timedelta(minutes=0)
    elif ago.endswith("m ago"):
        delta = timedelta(minutes=int(ago.split(" ")[0][:-1]))
    elif ago.endswith("h ago"):
        delta = timedelta(hours=int(ago.split(" ")[0][:-1]))
    elif ago.endswith("d ago"):
        delta = timedelta(days=int(ago.split(" ")[0][:-1]))
    else:
        delta = timedelta()
    return (current_time - delta).strftime("%Y-%m-%d")

def posted_hour(current_time, ago):
    if ago.lower() == "just now":
        delta = timedelta(minutes=0)
    elif ago.endswith("m ago"):
        delta = timedelta(minutes=int(ago.split(" ")[0][:-1]))
    elif ago.endswith("h ago"):
        delta = timedelta(hours=int(ago.split(" ")[0][:-1]))
    elif ago.endswith("d ago"):
        return None
    else:
        delta = timedelta()
    return (current_time - delta).hour

# Fully Selenium-based scraper
def scrape_jobs(output_file):
    jobs_list = []
    ended = False

    chrome_options = Options()
    chrome_options.binary_location = "/opt/chrome/chrome"
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--disable-gpu")

    driver = webdriver.Chrome("/opt/chromedriver", options=chrome_options)

    for page in range(1, 400):
        url = f"https://www.jobstreet.com.sg/jobs?daterange=2&page={page}&sortmode=ListedDate"
        driver.get(url)
        time.sleep(random.randint(3, 5))

        if "No matching search results" in driver.page_source:
            print("No more jobs.")
            break

        current_datetime = datetime.now() + timedelta(hours=8)
        job_cards = driver.find_elements(By.CSS_SELECTOR, '[data-testid="job-card"]')

        for card in job_cards:
            try:
                job_title_element = card.find_element(By.CSS_SELECTOR, '[data-automation="jobTitle"]')
                job_title = job_title_element.text
                href = job_title_element.get_attribute("href")
                job_id = href.split("/")[2].split("?")[0] if href else ""
                job_url = f"https://www.jobstreet.com.sg/job/{job_id}"
            except NoSuchElementException:
                continue

            try:
                company_element = card.find_element(By.CSS_SELECTOR, '[data-automation="jobCompany"]')
                company_name = company_element.text
                adv_url = company_element.get_attribute("href")
                category = "MCF" if adv_url and '61941084' in adv_url else "OK"
            except NoSuchElementException:
                company_name = "Private Advertiser"
                adv_url = "PRIVATE"
                category = "PRIVATE"

            location_elements = card.find_elements(By.CSS_SELECTOR, '[data-automation="jobLocation"]')
            job_locations = [loc.text for loc in location_elements]
            job_location_specific = job_locations[0] if len(job_locations) > 1 else ""
            job_region = job_locations[1] if len(job_locations) > 1 else job_locations[0] if job_locations else ""

            try:
                job_type_text = card.find_element(By.XPATH, "//*[contains(text(),'This is a')]").text
                match = re.search(r'This is a (\w+) job', job_type_text)
                job_type = match.group(1)
                job_type = f"{job_type} Time" if job_type in ["Full", "Part"] else job_type
            except:
                job_type = ""

            try:
                job_salary = card.find_element(By.CSS_SELECTOR, '[data-automation="jobSalary"]').text
            except NoSuchElementException:
                job_salary = ""

            try:
                ago = card.find_element(By.CSS_SELECTOR, '[data-automation="jobListingDate"]').text
            except NoSuchElementException:
                ago = ""

            if ago.endswith("d ago"):
                ended = True
                break

            job_listing_date = posted_date(current_datetime, ago)
            job_hour = posted_hour(current_datetime, ago)

            try:
                job_classification = card.find_element(By.CSS_SELECTOR, '[data-automation="jobClassification"]').text
                job_classification = job_classification.replace("(", "").replace(")", "")
            except NoSuchElementException:
                job_classification = ""

            try:
                job_sub_classification = card.find_element(By.CSS_SELECTOR, '[data-automation="jobSubClassification"]').text
            except NoSuchElementException:
                job_sub_classification = ""

            job_details = {
                "job_title": job_title,
                "job_id": job_id,
                "job_url": job_url,
                "job_cat": category,
                "adv_url": adv_url,
                "company": company_name,
                "job_type": job_type,
                "job_region": job_region,
                "job_location_specific": job_location_specific,
                "job_salary": job_salary,
                "job_date": job_listing_date,
                "job_hour": job_hour,
                "job_classification": job_classification,
                "job_sub_classification": job_sub_classification,
            }

            jobs_list.append(job_details)

        if ended:
            break

        time.sleep(random.randint(2, 4))

    driver.quit()

    df = pd.DataFrame(jobs_list)
    df.to_json(output_file, orient='records', lines=True)
    return output_file

# Main Lambda handler
def lambda_handler(event, context):
    label = convert_event_time(datetime.now() + timedelta(hours=8))
    output_file = f"/tmp/jobs-{label}.json"
    bucket_name = 'testing-bucket-6969'
    object_name = f'jobs-{label}.json'

    file_path = scrape_jobs(output_file)
    upload_to_s3(file_path, bucket_name, object_name)

    return {
        'statusCode': 200,
        'body': json.dumps('Script executed successfully and file uploaded to S3.')
    }


'''
Additional notes for deployment:

Use selenium and AWS
⚠️ Important AWS Lambda Considerations with Selenium
Lambda runs in a headless Linux environment, so you’ll need a headless version of Chrome (Chromium) and a compatible ChromeDriver.

These binaries are not included by default and need to be either:

Layered in via Lambda Layers (popular option)

Or packaged along with your deployment zip (larger and messier)

The output file needs to be saved in /tmp/ (Lambda’s only writable directory).

✅ 1. Lambda-compatible version of Selenium and Chromium
You'll need to use a prebuilt headless Chromium + ChromeDriver layer, such as:

Layer source: alixaxel/chrome-aws-lambda

Use this ARN in Lambda (for ap-southeast-1 for example):
arn:aws:lambda:ap-southeast-1:764866452798:layer:chrome-aws-lambda:37

Be sure to add this layer to your Lambda function in the AWS Console

✅ 2. Updated lambda_function.py Using Selenium + S3 Upload

The code above is a Selenium + S3-compatible version of your Lambda function script
'''