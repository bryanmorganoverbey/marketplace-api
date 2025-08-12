import requests
import json
import copy

GRAPHQL_URL = "https://www.facebook.com/api/graphql/"
GRAPHQL_HEADERS = {
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.74 Safari/537.36"
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
        for _ in range(1, numPageResults):
            pageInfo = facebookResponseJSON["data"]["marketplace_search"]["feed_units"]["page_info"]

            # If a next page of results exists
            if (pageInfo["has_next_page"]):
                cursor = facebookResponseJSON["data"]["marketplace_search"]["feed_units"]["page_info"]["end_cursor"]

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
                    return (status, error, data)
    else:
        return (status, error, data)

    # Parse the raw page results and set as the value of listingPages
    data["listingPages"] = parsePageResults(rawPageResults)
    return (status, error, data)


# Helper function
def getFacebookResponse(requestPayload):
    status = "Success"
    error = {}

    # Try making post request to Facebook, excpet return
    try:
        facebookResponse = requests.post(
            GRAPHQL_URL, headers=GRAPHQL_HEADERS, data=requestPayload)
    except requests.exceptions.RequestException as requestError:
        status = "Failure"
        error["source"] = "Request"
        error["message"] = str(requestError)
        facebookResponse = None
        return (status, error, facebookResponse)

    if (facebookResponse.status_code == 200):
        facebookResponseJSON = json.loads(facebookResponse.text)

        if (facebookResponseJSON.get("errors")):
            status = "Failure"
            error["source"] = "Facebook"
            error["message"] = facebookResponseJSON["errors"][0]["message"]
    else:
        status = "Failure"
        error["source"] = "Facebook"
        error["message"] = "Status code {}".format(
            facebookResponse.status_code)

    return (status, error, facebookResponse)


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
