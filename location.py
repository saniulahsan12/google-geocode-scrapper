from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import undetected_chromedriver as uc
import time
import random
from bs4 import BeautifulSoup
import re
import json
import csv
from pymongo import MongoClient
from datetime import datetime, timezone
import ssl
import certifi

# MongoDB connection
client = MongoClient(
    "XXXXXXXXXXXXXXXXXXXXXXXXX",
    tls=True,
    tlsCAFile=certifi.where()
)
db = client["DB_NAME"]
collection = db["COLLECTION_NAME"]

# Function to clean address text
def clean_address(text):
    if not text:
        return None
    
    stop_words = [
        "Open", "Closes", "24 hours", "Directions", "Website", 
        "On-site", "services", "Open⋅", "·Open", "·Closes",
        "Call", "Phone", "Hours", "Website", "Directions",
        "Closed", "·Closed", "pick-up · Delivery", "pick-up", 
        "· Delivery", "Delivery"
    ]
    
    text_lower = text.lower()
    earliest_pos = len(text)
    
    for word in stop_words:
        pos = text_lower.find(word.lower())
        if pos != -1 and pos < earliest_pos:
            earliest_pos = pos
    
    if earliest_pos < len(text):
        text = text[:earliest_pos]
    
    text = text.strip()
    while text and not (text[-1].isalnum() or text[-1] == ','):
        text = text[:-1].strip()
    
    text = re.sub(r'\d+\.\d+\(\d+\)', '', text)
    text = re.sub(r'·+\s*[^·\d]+\s*·+', ' ', text)
    text = re.sub(r'\d{2,3}[-\s]\d{6,8}', '', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'·+', ' · ', text)
    text = re.sub(r'\s+', ' ', text)
    text = text.strip(' ·-,')
    
    return text

# Function to extract latitude and longitude from Google Maps URL
def extract_lat_lng_from_google_maps_url(url):
    match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', url)
    if match:
        lat, lng = match.groups()
        return float(lat), float(lng)
    else:
        return None, None

# Function to scroll and load more content
def scroll_to_load(driver, scroll_times=30):
    try:
        scrollable_div = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//div[@role="feed"]'))
        )
    except (NoSuchElementException, TimeoutException):
        print("⚠️ No scrollable feed found. Skipping scroll.")
        return

    last_height = 0
    for _ in range(scroll_times):
        driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scrollable_div)
        time.sleep(random.uniform(1.5, 3))
        new_height = driver.execute_script('return arguments[0].scrollHeight', scrollable_div)
        if new_height == last_height:
            break
        last_height = new_height

# Function to extract location data from Google Maps
def extract_location_id_from_criteria(criteria, parentId):
    options = uc.ChromeOptions()
    options.add_argument("--lang=en-US,en")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    options.add_argument("--headless=new")

    driver = None
    try:
        driver = uc.Chrome(options=options, version_main=135)
        driver.get('https://www.google.com/maps?hl=en')
        time.sleep(random.uniform(5, 7))  # Wait for page load

        driver.delete_all_cookies()
        time.sleep(random.uniform(1, 2))

        # Locate search box
        try:
            search_box = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "searchboxinput"))
            )
            search_box.clear()
            search_box.send_keys(criteria)
            search_box.send_keys(Keys.ENTER)
            time.sleep(random.uniform(8, 12))  # Wait for search results
        except TimeoutException:
            print(f"⚠️ Search box ('searchboxinput') not found for criteria: {criteria}")
            return

        scroll_to_load(driver, scroll_times=50)

        # Locate feed div
        try:
            places_div = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//div[@role="feed"]'))
            )
            div_html = places_div.get_attribute('outerHTML')
            if not div_html:
                print("⚠️ No HTML content found in feed div.")
                return
        except TimeoutException:
            print("⚠️ No feed div found.")
            return

        soup = BeautifulSoup(div_html, "html.parser")
        seen_urls = set()

        for card in soup.find_all("div", recursive=True):
            try:
                name_tag = card.find("a", attrs={"aria-label": True})
                if not name_tag:
                    continue

                name = name_tag.get("aria-label")
                url = name_tag.get("href")
                lat, lng = extract_lat_lng_from_google_maps_url(url)

                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                address = None
                accessibility_icons = card.find_all("img", alt=lambda x: x and "wheelchair accessible" in x.lower())
                for icon in accessibility_icons:
                    parent = icon.parent
                    if parent:
                        next_sibling = parent.find_next_sibling()
                        if next_sibling:
                            address = next_sibling.get_text(strip=True)
                            break

                if not address:
                    address_candidates = []
                    for div in card.find_all("div"):
                        text = div.get_text(strip=True)
                        if re.search(r'\d+.*,', text) and len(text) > 5 and len(text) < 150:
                            address_candidates.append(text)
                    if address_candidates:
                        address = address_candidates[0]

                if not address:
                    for element in card.select('div[role="img"] + div'):
                        text = element.get_text(strip=True)
                        if text and len(text) > 5:
                            address = text
                            break

                place = {
                    "name": name,
                    "latitude": lat,
                    "longitude": lng,
                    "address": clean_address(address.split("·")[1]) if address else None,
                }

                if lat and lng:
                    print(json.dumps(place, indent=2, ensure_ascii=False))
                    existing = collection.find_one({"name": name})
                    if not existing:
                        document = {
                            "name": name,
                            "type": "union",
                            "createdAt": datetime.now(timezone.utc),
                            "updatedAt": datetime.now(timezone.utc),
                            "long_lat": [lng, lat],
                            "parent": parentId,
                            "address": clean_address(address.split("·")[1]) if address else None,
                        }
                        collection.insert_one(document)
                        print(f"✅ Inserted into database: {name}")
                    else:
                        print(f"⚡ Skipped duplicate: {name}")

            except Exception as e:
                print(f"Error parsing card: {e}")

    except Exception as e:
        print(f"Unexpected error: {e}")

    finally:
        if driver:
            try:
                driver.quit()
                print("✅ Driver closed successfully.")
            except Exception as e:
                print(f"⚠️ Error closing driver: {e}")

# Main loop
if __name__ == "__main__":
    file_path = 'locations.csv'

    while True:
        with open(file_path, mode='r', encoding='utf-8') as file:
            reader = list(csv.reader(file))

        if not reader:
            break

        row = reader[0]
        extract_location_id_from_criteria(row[0], row[1])

        with open(file_path, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerows(reader[1:])
