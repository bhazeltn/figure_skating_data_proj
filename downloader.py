#!/usr/bin/python3

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver import Firefox
import re
import requests
import concurrent.futures
import os

missing_urls = []

def read_urls(file_path):
    with open(file_path) as f:
        urls = [line.strip() for line in f]
    return urls

import re

import re

def scrape_pdf_urls(url):
    print(f'Attempting to get PDF URLS for {url}')
    options = webdriver.FirefoxOptions()
    options.add_argument('-headless')
    driver = Firefox(options=options)

    # Open the webpage
    driver.get(url)

    # Find all the links with the text "RESULTS" and the onclick attribute
    result_links = driver.find_elements(By.XPATH, "//a[text()='RESULTS'][@onclick]")

    # Find all the links with the text "Results" and the href attribute
    result_links_direct = driver.find_elements(By.XPATH, "//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'results')]")

    # Extract the PDF URLs from the onclick attribute
    base_url = 'https://skateabnwtnun.ca/'
    pdf_urls = []
    
    categories_to_exclude = ['star2', 'star-2', 'star3', 'star-3', 'star4', 'star-4', 'team']
    
    for link in result_links:
        onclick_attr = link.get_attribute("onclick")
        pdf_url = onclick_attr.split("('/")[1].split(".pdf'")[0] + ".pdf"
        pdf_url = base_url + pdf_url
        # STAR 4 is not to be included in this data set because it does not use IJS
        
        if ('CR-' in pdf_url or 'CR.' in pdf_url) and not any(word in pdf_url.lower() for word in categories_to_exclude):
            pdf_urls.append(pdf_url)

    # Extract the PDF URLs from the href attribute
    for link in result_links_direct:
        href_attr = link.get_attribute("href")
        # Only get Category Results Summary sheets from the older style archive. These will end in CR.pdf or CR-#.pdf
        if href_attr and (href_attr.endswith("CR.pdf") or re.match(r".*CR-\d+\.pdf$", href_attr)): 
            pdf_url = href_attr
            if pdf_url.startswith('/'):
                pdf_url = base_url + pdf_url[1:]
            if ('CR-' in pdf_url or 'CR.' in pdf_url) and not any(word in pdf_url.lower() for word in categories_to_exclude):
                pdf_urls.append(pdf_url)
        
        # Extract PDF URLs with query parameters
        if href_attr and href_attr.endswith(".pdf") and "?" in href_attr:
            pdf_urls.append(href_attr.replace("?", ""))

        # Extract PDF URLs with query parameters using regular expressions
        pdf_urls_with_query = re.findall(r'(?P<url>https?://\S+\.pdf\?.+)', href_attr)
        for pdf_url in pdf_urls_with_query:
            pdf_urls.append(pdf_url.replace("?", ""))

    # Close the browser
    driver.quit()
    return pdf_urls





def download_pdfs(pdf_urls, output_dir):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
    }

    for url in pdf_urls:
        # Get the filename from the URL
        filename = url.split('/')[-1]

        # Send a GET request to the URL and save the PDF file to the specified output directory
        response = requests.get(url, headers=headers)
        if 'The page you are looking for is no longer here' in response.text:
            print(f'Skipping file {url} as it does not exist on the server.')
            missing_urls.append(url)
        else:
            with open(os.path.join(output_dir, filename), 'wb') as f:
                f.write(response.content)
                print(f'Saved file {filename} to {output_dir}')
            

def download_pdfs_wrapper(url):
    download_pdfs(scrape_pdf_urls(url), 'pdfs')

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    futures = []
    for url in read_urls('urls.txt'):
        futures.append(executor.submit(download_pdfs_wrapper, url))
    for future in concurrent.futures.as_completed(futures):
        try:
            future.result()
        except Exception as exc:
            print(f'Thread error: {exc}')

with open('missing_urls.txt', 'w') as file:
    for filename in missing_urls:
        file.write(filename + '\n')
