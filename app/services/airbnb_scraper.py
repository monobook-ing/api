from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from openai import OpenAI
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)

AIRBNB_URL_PATTERN = re.compile(
    r"^https?://(?:www\.)?airbnb\.[a-z.]+/rooms/(\d+)"
)

FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class ScrapedListing(BaseModel):
    name: str
    type: str
    description: str
    images: list[str]
    price_per_night: float
    max_guests: int
    bed_config: str
    amenities: list[str]


def validate_airbnb_url(url: str) -> str:
    """Validate and normalize an Airbnb listing URL. Returns canonical URL."""
    url = url.strip()
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url

    match = AIRBNB_URL_PATTERN.match(url)
    if not match:
        raise ValueError(
            "Not a valid Airbnb listing URL. "
            "Expected format: airbnb.com/rooms/<id>"
        )

    listing_id = match.group(1)
    return f"https://www.airbnb.com/rooms/{listing_id}"


async def fetch_airbnb_page(url: str) -> str:
    """Fetch raw HTML from an Airbnb listing URL."""
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(15.0),
        headers=FETCH_HEADERS,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


# ---------------------------------------------------------------------------
# Static parsing helpers
# ---------------------------------------------------------------------------

def _extract_json_ld(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict) and data.get("@type"):
                return data
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type"):
                        return item
        except json.JSONDecodeError:
            continue
    return None


def _extract_meta_tags(soup: BeautifulSoup) -> dict[str, str]:
    meta: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        prop = tag.get("property", "") or tag.get("name", "")
        content = tag.get("content", "")
        if prop and content:
            meta[prop] = content
    return meta


def _walk_dict(data: dict | list, target_keys: set[str]) -> dict:
    """Recursively search a nested dict/list for specific keys."""
    found: dict = {}
    if isinstance(data, dict):
        for key, value in data.items():
            if key in target_keys and value:
                found[key] = value
            if isinstance(value, (dict, list)):
                found.update(_walk_dict(value, target_keys - set(found.keys())))
            if len(found) == len(target_keys):
                return found
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                found.update(_walk_dict(item, target_keys - set(found.keys())))
            if len(found) == len(target_keys):
                return found
    return found


def _extract_images_from_embedded(data: dict | list) -> list[str]:
    """Try to find image URLs from Airbnb's embedded JSON structure."""
    images: list[str] = []

    if isinstance(data, dict):
        # Check common Airbnb photo patterns
        for key in ("photos", "photoUrls", "images", "pictureUrls"):
            val = data.get(key)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and item.startswith("http"):
                        images.append(item)
                    elif isinstance(item, dict):
                        for url_key in ("baseUrl", "url", "large", "picture", "scrimColor"):
                            u = item.get(url_key, "")
                            if isinstance(u, str) and u.startswith("http"):
                                images.append(u)
                                break
        if images:
            return images

        for value in data.values():
            if isinstance(value, (dict, list)):
                images = _extract_images_from_embedded(value)
                if len(images) >= 3:
                    return images
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                images = _extract_images_from_embedded(item)
                if len(images) >= 3:
                    return images
    return images


def _extract_embedded_json(soup: BeautifulSoup) -> dict | None:
    """Try to find Airbnb's bootstrapped data payload in script tags."""
    # Look for deferred state scripts (Airbnb's Next.js data)
    for script in soup.find_all("script", id=True):
        script_id = script.get("id", "")
        if "deferred-state" in script_id or "data-state" in script_id:
            text = script.string or ""
            if len(text) > 500:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    continue

    # Fallback: look for large JSON script blocks
    for script in soup.find_all("script"):
        text = script.string or ""
        if len(text) > 5000 and "{" in text:
            start = text.find("{")
            if start >= 0:
                try:
                    return json.loads(text[start:])
                except json.JSONDecodeError:
                    pass
    return None


def _parse_price_text(text: str) -> float | None:
    """Extract a numeric price from a text string like '$195' or '195 USD'."""
    match = re.search(r"[\$€£]?\s*(\d[\d,]*(?:\.\d{1,2})?)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def _extract_amenities_from_html(soup: BeautifulSoup) -> list[str]:
    """Extract amenities from Airbnb's deferred state using regex.

    Airbnb stores amenities as {"available":true,"title":"Wifi",...} objects.
    """
    amenities: list[str] = []
    for script in soup.find_all("script", id=True):
        text = script.string or ""
        if len(text) < 1000:
            continue
        for m in re.finditer(
            r'"available"\s*:\s*true\s*,\s*"title"\s*:\s*"([^"]+)"', text
        ):
            title = m.group(1)
            if title not in amenities:
                amenities.append(title)
        if amenities:
            break
    return amenities


def _parse_og_title(og_title: str) -> dict:
    """Parse Airbnb og:title like 'Home in Vysloboky · ★4.99 · 1 bedroom · 1 bed · 1 bath'."""
    result: dict = {}
    parts = [p.strip() for p in og_title.split("·")]
    if parts:
        first = parts[0].strip()
        # First part is usually "Home in City" or "Entire villa in City"
        first_lower = first.lower()
        for label in [
            "entire home", "entire villa", "villa", "apartment", "condo",
            "private room", "shared room", "loft", "studio", "cottage",
            "cabin", "house", "bungalow", "townhouse", "home",
        ]:
            if first_lower.startswith(label):
                result["room_type"] = label.title()
                break

    bed_parts = [p.strip() for p in parts if re.search(r"\d+\s*(bed|bath)", p, re.IGNORECASE)]
    if bed_parts:
        result["bed_config"] = " · ".join(bed_parts)
    return result


def _parse_static(html: str) -> ScrapedListing | None:
    """Attempt to extract listing data from raw HTML using static parsing."""
    soup = BeautifulSoup(html, "html.parser")

    json_ld = _extract_json_ld(soup)
    meta = _extract_meta_tags(soup)
    embedded = _extract_embedded_json(soup)

    name: str | None = None
    description: str = ""
    images: list[str] = []
    price: float | None = None
    max_guests: int = 2
    bed_config: str = ""
    amenities: list[str] = []
    room_type: str = ""

    # --- JSON-LD extraction (most reliable for name, description, images) ---
    if json_ld:
        name = json_ld.get("name")
        description = json_ld.get("description", "")
        img = json_ld.get("image")
        if isinstance(img, list):
            images = [
                i if isinstance(i, str) else i.get("url", "")
                for i in img
                if (isinstance(i, str) and i.startswith("http"))
                or (isinstance(i, dict) and i.get("url", "").startswith("http"))
            ]
        elif isinstance(img, str) and img.startswith("http"):
            images = [img]

        # Price from JSON-LD offers (may not exist on Airbnb pages)
        offers = json_ld.get("offers")
        if isinstance(offers, dict):
            p = offers.get("price") or offers.get("lowPrice")
            if p is not None:
                try:
                    price = float(p)
                except (ValueError, TypeError):
                    pass
        elif isinstance(offers, list) and offers:
            p = offers[0].get("price") or offers[0].get("lowPrice")
            if p is not None:
                try:
                    price = float(p)
                except (ValueError, TypeError):
                    pass

        # Person capacity from JSON-LD containsPlace.occupancy
        contains = json_ld.get("containsPlace")
        if isinstance(contains, dict):
            occ = contains.get("occupancy")
            if isinstance(occ, dict):
                val = occ.get("value")
                if isinstance(val, int) and val > 0:
                    max_guests = val

    # --- Embedded JSON extraction ---
    if embedded:
        target_keys = {"personCapacity"}
        if price is None:
            target_keys.add("priceString")
            target_keys.add("price")

        found = _walk_dict(embedded, target_keys)

        if price is None:
            price_val = found.get("priceString") or found.get("price")
            if isinstance(price_val, (int, float)):
                price = float(price_val)
            elif isinstance(price_val, str):
                price = _parse_price_text(price_val)

        cap = found.get("personCapacity")
        if isinstance(cap, int) and cap > 0:
            max_guests = cap

        if not images:
            images = _extract_images_from_embedded(embedded)

    # --- Amenities from deferred state ---
    if not amenities:
        amenities = _extract_amenities_from_html(soup)

    # --- Meta tags / og:title fallback ---
    og_title = meta.get("og:title", "")
    if not name:
        name = re.sub(r"\s*[-–—]\s*Airbnb.*$", "", og_title).strip() or None
    if not description:
        description = meta.get("og:description", "")
    if not images:
        og_image = meta.get("og:image")
        if og_image and og_image.startswith("http"):
            images = [og_image]

    # Parse bed config and room type from og:title
    og_parsed = _parse_og_title(og_title)
    if not bed_config:
        bed_config = og_parsed.get("bed_config", "")
    if not room_type:
        room_type = og_parsed.get("room_type", "")

    # Infer room type from <title> tag, name, or description
    if not room_type:
        title_tag = soup.find("title")
        check_texts = [name or "", description, title_tag.string if title_tag else ""]
        combined_lower = " ".join(check_texts).lower()
        for label in [
            "entire home", "entire villa", "villa", "apartment", "condo",
            "private room", "shared room", "loft", "studio", "cottage",
            "cabin", "house", "bungalow", "townhouse",
        ]:
            if label in combined_lower:
                room_type = label.title()
                break
    if not room_type:
        room_type = "Entire home"

    # Validate minimum required fields
    if not name:
        return None

    # Airbnb often doesn't expose price without dates selected.
    # If we have everything else, return with price=0 so LLM or caller can handle.
    # The endpoint will attempt LLM fallback if price is missing.
    return ScrapedListing(
        name=name,
        type=room_type,
        description=description,
        images=images[:20],
        price_per_night=price if price and price > 0 else 0,
        max_guests=max_guests,
        bed_config=bed_config,
        amenities=amenities,
    )


# ---------------------------------------------------------------------------
# LLM fallback
# ---------------------------------------------------------------------------

async def _parse_with_llm(html: str) -> ScrapedListing | None:
    """Use LLM to extract listing data when static parsing fails."""
    settings = get_settings()
    if not settings.openai_api_key:
        return None

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "svg", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = text[:12000]

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.agent_model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a data extraction assistant. Extract Airbnb listing details "
                        "from the provided text content. Return a JSON object with these fields:\n"
                        '- "name" (string, listing title)\n'
                        '- "type" (string, e.g. "Entire home", "Private room", "Villa")\n'
                        '- "description" (string, listing description)\n'
                        '- "images" (array of image URL strings, empty array if none found)\n'
                        '- "price_per_night" (number, nightly price in the listed currency, 0 if not found)\n'
                        '- "max_guests" (integer, maximum number of guests, 2 if not found)\n'
                        '- "bed_config" (string, e.g. "1 King Bed + 2 Single Beds")\n'
                        '- "amenities" (array of strings)\n'
                        "Extract only what you can find. Do not fabricate data."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Extract the Airbnb listing details from this page content:\n\n{text}",
                },
            ],
            temperature=0,
        )

        data = json.loads(response.choices[0].message.content or "{}")
        if not data.get("name"):
            return None

        price = float(data.get("price_per_night", 0))
        if price <= 0:
            return None

        return ScrapedListing(
            name=data["name"],
            type=data.get("type", "Entire home"),
            description=data.get("description", ""),
            images=[
                u for u in data.get("images", [])
                if isinstance(u, str) and u.startswith("http")
            ],
            price_per_night=price,
            max_guests=int(data.get("max_guests", 2)),
            bed_config=data.get("bed_config", ""),
            amenities=[a for a in data.get("amenities", []) if isinstance(a, str)],
        )
    except Exception as e:
        logger.warning("LLM extraction failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def scrape_airbnb_listing(url: str) -> ScrapedListing:
    """Scrape an Airbnb listing URL and return structured data.

    Strategy: validate URL → fetch HTML → static parse → LLM fallback.
    Raises ValueError with user-friendly messages on failure.
    """
    canonical_url = validate_airbnb_url(url)

    try:
        html = await fetch_airbnb_page(canonical_url)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            raise ValueError("Airbnb blocked this request. Please try again later.")
        if e.response.status_code == 404:
            raise ValueError("Airbnb listing not found. Please check the URL.")
        raise ValueError(f"Failed to fetch Airbnb page: {e.response.status_code}")
    except httpx.TimeoutException:
        raise ValueError("Request to Airbnb timed out. Please try again.")
    except httpx.RequestError as e:
        raise ValueError(f"Could not connect to Airbnb: {e}")

    # Step 1: Try static parsing
    static_listing = _parse_static(html)

    # Step 2: If static got data but price is missing, try LLM to fill price
    if static_listing and static_listing.price_per_night > 0:
        logger.info("Static parsing succeeded for %s", canonical_url)
        return static_listing

    # Step 3: LLM fallback (full extraction or price-only)
    llm_listing = await _parse_with_llm(html)

    if static_listing and llm_listing:
        # Merge: use static data with LLM price
        logger.info("Merging static + LLM data for %s", canonical_url)
        return ScrapedListing(
            name=static_listing.name,
            type=static_listing.type,
            description=static_listing.description,
            images=static_listing.images or llm_listing.images,
            price_per_night=llm_listing.price_per_night,
            max_guests=static_listing.max_guests,
            bed_config=static_listing.bed_config or llm_listing.bed_config,
            amenities=static_listing.amenities or llm_listing.amenities,
        )

    if llm_listing:
        logger.info("LLM extraction succeeded for %s", canonical_url)
        return llm_listing

    # Static data without price — still usable, owner can edit price later
    if static_listing:
        logger.info("Static parsing succeeded (no price) for %s", canonical_url)
        return static_listing

    raise ValueError(
        "Could not extract listing details from this Airbnb page. "
        "The page may require JavaScript rendering, or the listing may be unavailable."
    )
