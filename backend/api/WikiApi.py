import requests
import re
from urllib.parse import urlparse, unquote
import sys
import time
import logging
sys.stdout.reconfigure(encoding='utf-8')

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_wikipedia_data(url: str):
    logger.info(f"Starting Wikipedia API request for URL: {url}")
    
    # Extract title from URL (e.g. '/wiki/Battle_of_Verdun' → 'Battle_of_Verdun')
    path = urlparse(url).path
    title = unquote(path.split('/wiki/')[-1])
    logger.info(f"Extracted title: {title}")

    api_url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "titles": title,
        "prop": "coordinates|extracts",
        "explaintext": True,
        "exintro": True,
        "format": "json"
    }
    logger.info(f"API params: {params}")

    headers = {
        "User-Agent": "HistoryAsAMap/1.0 (https://github.com/yourusername/history-as-a-map; your.email@example.com) Python-requests/2.x"
    }
    logger.info(f"Request headers: {headers}")

    try:
        # Add delay to avoid rate limiting
        logger.info("Waiting 1 second before request...")
        time.sleep(1)
        
        logger.info(f"Making request to: {api_url}")
        start_time = time.time()
        response = requests.get(api_url, params=params, headers=headers, timeout=10)
        request_time = time.time() - start_time
        
        logger.info(f"Response received in {request_time:.2f} seconds")
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")
        
        if response.status_code != 200:
            logger.error(f"Non-200 status code: {response.status_code}")
            logger.error(f"Response body: {response.text}")
        
        response.raise_for_status()
        data = response.json()
        logger.info(f"Successfully parsed JSON response")

        page = next(iter(data["query"]["pages"].values()))
        logger.info(f"Page data: {page}")
        
        title_clean = page.get("title", "")
        logger.info(f"Clean title: {title_clean}")
        
        coords = page.get("coordinates", [{}])[0]
        lat, lon = coords.get("lat"), coords.get("lon")
        logger.info(f"Coordinates: lat={lat}, lon={lon}")

        # Extract text and detect date
        extract = page.get("extract", "")
        first_paragraph = extract.split("\n")[0].strip()
        logger.info(f"Extract length: {len(extract)} chars")
        logger.info(f"First paragraph: {first_paragraph[:100]}...")

        # Try to find a single date (like "21 February 1916")
        date_matches = re.findall(r"\b(\d{1,2}\s+\w+\s+\d{4})\b", extract)
        date = date_matches[0] if len(set(date_matches)) == 1 else None
        logger.info(f"Date matches: {date_matches}, selected: {date}")

        # Always extract the first year mentioned
        year_match = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", extract)
        year = year_match.group(1) if year_match else None
        logger.info(f"Year match: {year}")

        result = {
            "title": title_clean,
            "coordinates": (lat, lon) if lat and lon else None,
            "first_paragraph": first_paragraph,
            "date": date,
            "year": year,
            "link": url
        }
        logger.info(f"Returning result: {result}")
        return result

    except requests.exceptions.RequestException as e:
        logger.error(f"Request exception for {url}: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error for {url}: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

