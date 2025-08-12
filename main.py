import asyncio
from typing import Any, Dict, List

from apify import Actor

from MarketplaceScraper import searchListings


async def run_actor() -> None:
    async with Actor:
        actor_input: Dict[str, Any] = await Actor.get_input() or {}
        location_query: str = actor_input.get("locationQuery")
        listing_query: str = actor_input.get("listingQuery")
        num_page_results: int = int(actor_input.get("numPageResults", 1))

        if not location_query or not listing_query:
            await Actor.set_status_message("Missing required input: 'locationQuery' and 'listingQuery' are required.")
            await Actor.push_data({
                "status": "Failure",
                "error": {
                    "source": "User",
                    "message": "Missing required input: 'locationQuery' and 'listingQuery' are required."
                },
            })
            return

        status, error, data = searchListings(
            location_query, listing_query, num_page_results)

        if status != "Success":
            await Actor.set_status_message(f"Error: {error.get('message', 'Unknown error')}")
            # Still push the error for visibility
            await Actor.push_data({
                "status": status,
                "error": error,
            })
            return

        pages: List[Dict[str, Any]] = data.get("listingPages", [])
        items: List[Dict[str, Any]] = []
        for page in pages:
            for item in page.get("listings", []):
                items.append(item)

        if not items:
            await Actor.set_status_message("No listings found.")
            await Actor.push_data({
                "status": status,
                "listings_count": 0,
                "locationQuery": location_query,
                "listingQuery": listing_query,
            })
            return

        await Actor.set_status_message(f"Pushing {len(items)} listings to dataset…")
        await Actor.push_data(items)


if __name__ == "__main__":
    asyncio.run(run_actor())
