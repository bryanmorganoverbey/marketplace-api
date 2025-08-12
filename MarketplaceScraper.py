import requests
import json
import copy
import time
import random
from typing import Tuple, Dict, Any

GRAPHQL_URL = "https://www.facebook.com/api/graphql/"

# Rotate between different user agents to avoid detection
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0"
]


def get_random_headers():
    """Generate randomized headers to avoid detection"""
    return {
        "sec-fetch-site": "same-origin",
        "user-agent": random.choice(USER_AGENTS),
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.5",
        "accept-encoding": "gzip, deflate, br",
        "dnt": "1",
        "connection": "keep-alive",
        "upgrade-insecure-requests": "1",
    }


def getLocations(locationQuery):
    data = {}

    requestPayload = {
        "variables": """{"params": {"caller": "MARKETPLACE", "page_category": ["CITY", "SUBCITY", "NEIGHBORHOOD","POSTAL_CODE"], "query": "%s"}}""" % (locationQuery),
        "doc_id": "5585904654783609"
    }

    status, error, facebookResponse = getFacebookResponse(requestPayload)

    if (status == "Success"):
        data["locations"] = []  # Create a locations object within data
        facebookResponseJSON = json.loads(facebookResponse.text)

        # Get location names and their ID from the facebook response
        for location in facebookResponseJSON["data"]["city_street_search"]["street_results"]["edges"]:
            locationName = location["node"]["subtitle"].split(" \u00b7")[0]

            # Refine location name if it is too general
            if (locationName == "City"):
                locationName = location["node"]["single_line_address"]

            locationLatitude = location["node"]["location"]["latitude"]
            locationLongitude = location["node"]["location"]["longitude"]

            # Add the location to the list of locations
            data["locations"].append({
                "name": locationName,
                "latitude": str(locationLatitude),
                "longitude": str(locationLongitude)
            })

    return (status, error, data)


def getListings(locationLatitude, locationLongitude, listingQuery, numPageResults=1):
    data = {}

    rawPageResults = []  # Un-parsed list of JSON results from each page

    requestPayload = {
        "variables": """{"count":24, "params":{"bqf":{"callsite":"COMMERCE_MKTPLACE_WWW","query":"%s"},"browse_request_params":{"commerce_enable_local_pickup":true,"commerce_enable_shipping":true,"commerce_search_and_rp_available":true,"commerce_search_and_rp_condition":null,"commerce_search_and_rp_ctime_days":null,"filter_location_latitude":%s,"filter_location_longitude":%s,"filter_price_lower_bound":0,"filter_price_upper_bound":214748364700,"filter_radius_km":16},"custom_request_params":{"surface":"SEARCH"}}}""" % (listingQuery, locationLatitude, locationLongitude),
        "doc_id": "7111939778879383"
    }

    status, error, facebookResponse = getFacebookResponse(requestPayload)

    if (status == "Success"):
        facebookResponseJSON = json.loads(facebookResponse.text)
        rawPageResults.append(facebookResponseJSON)

        # Retrieve subsequent page results if numPageResults > 1
        for page_num in range(1, numPageResults):
            pageInfo = facebookResponseJSON["data"]["marketplace_search"]["feed_units"]["page_info"]

            # If a next page of results exists
            if (pageInfo["has_next_page"]):
                cursor = facebookResponseJSON["data"]["marketplace_search"]["feed_units"]["page_info"]["end_cursor"]

                # Add extra delay between pages to be more respectful
                print(f"Fetching page {page_num + 1}/{numPageResults}...")
                time.sleep(random.uniform(2, 4))

                # Make a copy of the original request payload
                requestPayloadCopy = copy.copy(requestPayload)

                # Insert the cursor object into the variables object of the request payload copy
                requestPayloadCopy["variables"] = requestPayloadCopy["variables"].split(
                )
                requestPayloadCopy["variables"].insert(
                    1, """"cursor":'{}',""".format(cursor))
                requestPayloadCopy["variables"] = "".join(
                    requestPayloadCopy["variables"])

                status, error, facebookResponse = getFacebookResponse(
                    requestPayloadCopy)

                if (status == "Success"):
                    facebookResponseJSON = json.loads(facebookResponse.text)
                    rawPageResults.append(facebookResponseJSON)
                else:
                    print(
                        f"Failed to fetch page {page_num + 1}: {error.get('message', 'Unknown error')}")
                    return (status, error, data)
            else:
                print(f"No more pages available after page {page_num}")
                break
    else:
        return (status, error, data)

    # Parse the raw page results and set as the value of listingPages
    data["listingPages"] = parsePageResults(rawPageResults)
    return (status, error, data)


# Helper function with retry logic and rate limiting
def getFacebookResponse(requestPayload, max_retries=3):
    """
    Make a request to Facebook GraphQL API with retry logic and rate limiting
    """
    status = "Success"
    error = {}

    for attempt in range(max_retries):
        # Add delay between requests to avoid rate limiting
        if attempt > 0:
            # Exponential backoff with jitter
            backoff_delay = (2 ** attempt) + random.uniform(1, 3)
            print(
                f"Rate limit detected, waiting {backoff_delay:.1f}s before retry {attempt + 1}/{max_retries}")
            time.sleep(backoff_delay)
        else:
            # Small random delay even on first request
            time.sleep(random.uniform(0.5, 2.0))

        try:
            # Use randomized headers for each request
            headers = get_random_headers()
            facebookResponse = requests.post(
                GRAPHQL_URL,
                headers=headers,
                data=requestPayload,
                timeout=30  # Add timeout to prevent hanging
            )
        except requests.exceptions.RequestException as requestError:
            if attempt == max_retries - 1:  # Last attempt
                status = "Failure"
                error["source"] = "Request"
                error["message"] = str(requestError)
                facebookResponse = None
                return (status, error, facebookResponse)
            continue

        # Check response status
        if facebookResponse.status_code == 200:
            try:
                facebookResponseJSON = json.loads(facebookResponse.text)

                if facebookResponseJSON.get("errors"):
                    error_msg = facebookResponseJSON["errors"][0]["message"]

                    # Check for rate limiting errors
                    if "rate limit" in error_msg.lower() or "too many requests" in error_msg.lower():
                        if attempt < max_retries - 1:
                            print(f"Rate limit error: {error_msg}")
                            continue  # Retry with exponential backoff

                    status = "Failure"
                    error["source"] = "Facebook"
                    error["message"] = error_msg
                    return (status, error, facebookResponse)

                # Success - return immediately
                return (status, error, facebookResponse)

            except json.JSONDecodeError:
                if attempt < max_retries - 1:
                    print("Invalid JSON response, retrying...")
                    continue
                status = "Failure"
                error["source"] = "Facebook"
                error["message"] = "Invalid JSON response"
                return (status, error, facebookResponse)

        elif facebookResponse.status_code == 429:  # Too Many Requests
            if attempt < max_retries - 1:
                print(f"HTTP 429 - Rate limited, retrying...")
                continue

        elif facebookResponse.status_code in [403, 401]:  # Access denied
            status = "Failure"
            error["source"] = "Facebook"
            error["message"] = f"Access denied (HTTP {facebookResponse.status_code}). May need updated headers or cookies."
            return (status, error, facebookResponse)

        else:
            if attempt < max_retries - 1:
                print(f"HTTP {facebookResponse.status_code}, retrying...")
                continue

    # If we get here, all retries failed
    status = "Failure"
    error["source"] = "Facebook"
    error["message"] = f"All {max_retries} attempts failed. Last status: HTTP {facebookResponse.status_code if 'facebookResponse' in locals() else 'Unknown'}"

    return (status, error, facebookResponse if 'facebookResponse' in locals() else None)


# Helper function
def parsePageResults(rawPageResults):
    listingPages = []

    pageIndex = 0
    for rawPageResult in rawPageResults:

        # Create a new listings object within the listingPages array
        listingPages.append({"listings": []})

        for listing in rawPageResult["data"]["marketplace_search"]["feed_units"]["edges"]:

            # If object is a listing
            if (listing["node"]["__typename"] == "MarketplaceFeedListingStoryObject"):
                node = listing.get("node", {})
                listing_node = node.get("listing") or {}

                listingID = listing_node.get("id", "")
                listingName = listing_node.get("marketplace_listing_title", "")

                listing_price = listing_node.get("listing_price") or {}
                listingCurrentPrice = listing_price.get("formatted_amount", "")

                strikethrough_price = listing_node.get(
                    "strikethrough_price") or {}
                listingPreviousPrice = strikethrough_price.get(
                    "formatted_amount", "")

                listingSaleIsPending = listing_node.get("is_pending", False)

                primary_listing_photo = listing_node.get(
                    "primary_listing_photo") or {}
                image = primary_listing_photo.get("image") or {}
                listingPrimaryPhotoURL = image.get("uri", "")

                seller = listing_node.get("marketplace_listing_seller") or {}
                sellerName = seller.get("name", "")
                sellerType = seller.get("__typename", "")

                location = listing_node.get("location") or {}
                reverse_geocode = location.get("reverse_geocode") or {}
                city_page = reverse_geocode.get("city_page") or {}
                sellerLocation = city_page.get("display_name", "")

                # Add the listing to its corresponding page
                listingPages[pageIndex]["listings"].append({
                    "id": listingID,
                    "name": listingName,
                    "currentPrice": listingCurrentPrice,
                    "previousPrice": listingPreviousPrice,
                    "saleIsPending": str(listingSaleIsPending).lower(),
                    "primaryPhotoURL": listingPrimaryPhotoURL,
                    "sellerName": sellerName,
                    "sellerLocation": sellerLocation,
                    "sellerType": sellerType
                })

        pageIndex += 1

    return listingPages


def searchListings(locationQuery: str, listingQuery: str, numPageResults: int = 1):
    status, error, locationData = getLocations(locationQuery)
    if status != "Success" or not locationData.get("locations"):
        return status, error, {}

    # Choose the first location match
    latitude = locationData["locations"][0]["latitude"]
    longitude = locationData["locations"][0]["longitude"]

    return getListings(latitude, longitude, listingQuery, numPageResults)
