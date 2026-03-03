from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel

from app.core.config import get_settings

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - local env may have OpenAI<1
    OpenAI = None

logger = logging.getLogger(__name__)

BOOKING_URL_PATTERN = re.compile(
    r"^https?://(?:www\.)?booking\.[a-z.]+/hotel/[^?#]+",
    re.IGNORECASE,
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

_CURRENCY_SYMBOL_MAP = {
    "$": "USD",
    "US$": "USD",
    "€": "EUR",
    "£": "GBP",
    "₴": "UAH",
    "¥": "JPY",
    "₺": "TRY",
}


class ScrapedBookingListing(BaseModel):
    name: str
    type: str
    description: str
    images: list[str]
    price_per_night: float
    currency_code: str = "USD"
    max_guests: int
    bed_config: str
    amenities: list[str]


def validate_booking_url(url: str) -> str:
    """Validate and normalize a Booking.com listing URL. Returns canonical URL."""
    url = url.strip()
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
        parsed = urlparse(url)

    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if not BOOKING_URL_PATTERN.match(url) or "booking." not in host or not path.startswith(
        "/hotel/"
    ):
        raise ValueError(
            "Not a valid Booking.com listing URL. "
            "Expected format: booking.com/hotel/<country>/<slug>.html"
        )

    canonical_path = re.sub(r"/+$", "", path)
    if not canonical_path:
        raise ValueError("Booking.com listing URL is missing the listing path.")

    return f"https://www.booking.com{canonical_path}"


async def fetch_booking_page(url: str) -> str:
    """Fetch raw HTML from a Booking.com listing URL."""
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(15.0),
        headers=FETCH_HEADERS,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


def _extract_json_ld_candidates(soup: BeautifulSoup) -> list[dict]:
    items: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue

        if isinstance(payload, dict):
            items.append(payload)
        elif isinstance(payload, list):
            items.extend([item for item in payload if isinstance(item, dict)])
    return items


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


def _extract_embedded_json(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or ""
        if len(text) < 5000 or "{" not in text:
            continue
        start = text.find("{")
        if start < 0:
            continue
        try:
            return json.loads(text[start:])
        except json.JSONDecodeError:
            continue
    return None


def _parse_price_text(text: str) -> float | None:
    match = re.search(r"[\$€£₴₺¥]?\s*(\d[\d,]*(?:\.\d{1,2})?)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def _parse_currency_code(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None

    upper = raw.upper()
    if len(upper) == 3 and upper.isalpha():
        return upper

    if raw in _CURRENCY_SYMBOL_MAP:
        return _CURRENCY_SYMBOL_MAP[raw]
    if upper in _CURRENCY_SYMBOL_MAP:
        return _CURRENCY_SYMBOL_MAP[upper]

    return None


def _extract_bed_config(text: str) -> str:
    matches = re.findall(
        r"\b\d+\s+(?:extra-large\s+double|large\s+double|double|single|queen|king|"
        r"sofa\s+bed|bunk|twin)\s+beds?\b",
        text,
        flags=re.IGNORECASE,
    )
    unique: list[str] = []
    for item in matches:
        normalized = re.sub(r"\s+", " ", item).strip()
        if normalized.lower() not in {existing.lower() for existing in unique}:
            unique.append(normalized)
        if len(unique) >= 3:
            break
    return " · ".join(unique)


def _extract_max_guests(raw_text: str) -> int | None:
    patterns = [
        r'"max_occupancy"\s*:\s*(\d+)',
        r'"maxOccupancy"\s*:\s*(\d+)',
        r'"number_of_guests"\s*:\s*(\d+)',
        r'"numberOfGuests"\s*:\s*(\d+)',
        r"\b(\d+)\s+(?:guests?|adults?)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if not match:
            continue
        value = int(match.group(1))
        if 1 <= value <= 20:
            return value
    return None


def _extract_amenities(soup: BeautifulSoup, raw_text: str) -> list[str]:
    amenities: list[str] = []

    def append_unique(candidate: str) -> None:
        text = candidate.strip()
        if not text or len(text) > 80:
            return
        if text.lower() not in {item.lower() for item in amenities}:
            amenities.append(text)

    for el in soup.select('[data-testid*="facilit"] li, [data-testid*="facilit"]'):
        append_unique(el.get_text(" ", strip=True))

    for match in re.finditer(r'"facility_name"\s*:\s*"([^"]+)"', raw_text):
        append_unique(match.group(1))

    return amenities


def _extract_images_from_embedded(raw_text: str) -> list[str]:
    image_urls = re.findall(
        r'https://[^"\']+\.(?:jpg|jpeg|png|webp|avif)(?:\?[^"\']*)?',
        raw_text,
        flags=re.IGNORECASE,
    )
    deduped: list[str] = []
    for url in image_urls:
        if "booking.com" not in url and "bstatic.com" not in url:
            continue
        if url not in deduped:
            deduped.append(url)
        if len(deduped) >= 20:
            break
    return deduped


def _infer_room_type(
    *,
    json_ld_type: object,
    name: str | None,
    description: str,
    fallback_text: str = "",
) -> str:
    values = [
        str(json_ld_type) if json_ld_type is not None else "",
        name or "",
        description,
        fallback_text,
    ]
    combined = " ".join(values).lower()

    if "apartment" in combined:
        return "Apartment"
    if "villa" in combined:
        return "Villa"
    if "suite" in combined:
        return "Suite"
    if "studio" in combined:
        return "Studio"
    if "hotel" in combined:
        return "Hotel Room"
    return "Apartment"


def _parse_static(html: str) -> ScrapedBookingListing | None:
    soup = BeautifulSoup(html, "html.parser")
    meta = _extract_meta_tags(soup)
    raw_text = html
    embedded = _extract_embedded_json(soup)

    name: str | None = None
    description: str = ""
    images: list[str] = []
    price: float | None = None
    currency_code: str = "USD"
    max_guests: int = 2
    bed_config: str = ""
    amenities: list[str] = []
    room_type: str = ""
    json_ld_type: object = None

    json_ld_candidates = _extract_json_ld_candidates(soup)
    json_ld_primary = next(
        (
            item
            for item in json_ld_candidates
            if "type" in item
            or "@type" in item
            or "offers" in item
            or "name" in item
        ),
        None,
    )

    if json_ld_primary:
        json_ld_type = json_ld_primary.get("@type")
        name = json_ld_primary.get("name")
        description = json_ld_primary.get("description", "")

        img = json_ld_primary.get("image")
        if isinstance(img, list):
            images = [value for value in img if isinstance(value, str) and value.startswith("http")]
        elif isinstance(img, str) and img.startswith("http"):
            images = [img]

        offers = json_ld_primary.get("offers")
        offer_payloads: list[dict] = []
        if isinstance(offers, dict):
            offer_payloads = [offers]
        elif isinstance(offers, list):
            offer_payloads = [item for item in offers if isinstance(item, dict)]

        for offer in offer_payloads:
            if price is None:
                p = offer.get("price") or offer.get("lowPrice")
                if isinstance(p, (int, float)):
                    price = float(p)
                elif isinstance(p, str):
                    price = _parse_price_text(p)
            if currency_code == "USD":
                parsed = _parse_currency_code(offer.get("priceCurrency"))
                if parsed:
                    currency_code = parsed
            if price is not None and currency_code != "USD":
                break

        amenity_feature = json_ld_primary.get("amenityFeature")
        if isinstance(amenity_feature, list):
            for item in amenity_feature:
                if isinstance(item, dict):
                    title = item.get("name")
                    if isinstance(title, str) and title.strip():
                        amenities.append(title.strip())

    if not name:
        og_title = meta.get("og:title", "")
        cleaned = re.sub(r"\s*[\-|–—|]\s*Booking\.com.*$", "", og_title, flags=re.IGNORECASE)
        name = cleaned.strip() or None

    if not description:
        description = meta.get("og:description", "")

    if not images:
        og_image = meta.get("og:image")
        if isinstance(og_image, str) and og_image.startswith("http"):
            images = [og_image]

    if embedded:
        found = _walk_dict(
            embedded,
            {
                "maxOccupancy",
                "max_occupancy",
                "numberOfGuests",
                "number_of_guests",
                "price",
                "priceAmount",
                "currency",
                "currencyCode",
                "bedroom_text",
                "roomName",
                "room_name",
            },
        )

        if price is None:
            raw_price = found.get("priceAmount") or found.get("price")
            if isinstance(raw_price, (int, float)):
                price = float(raw_price)
            elif isinstance(raw_price, str):
                price = _parse_price_text(raw_price)

        if currency_code == "USD":
            parsed_currency = _parse_currency_code(
                found.get("currencyCode") or found.get("currency")
            )
            if parsed_currency:
                currency_code = parsed_currency

        if max_guests == 2:
            guest_raw = (
                found.get("maxOccupancy")
                or found.get("max_occupancy")
                or found.get("numberOfGuests")
                or found.get("number_of_guests")
            )
            if isinstance(guest_raw, int) and guest_raw > 0:
                max_guests = guest_raw
            elif isinstance(guest_raw, str) and guest_raw.isdigit():
                max_guests = int(guest_raw)

        if not bed_config:
            room_beds = found.get("bedroom_text")
            if isinstance(room_beds, str):
                bed_config = _extract_bed_config(room_beds)

        if not room_type:
            room_name = found.get("roomName") or found.get("room_name")
            if isinstance(room_name, str):
                room_type = _infer_room_type(
                    json_ld_type=json_ld_type,
                    name=name,
                    description=description,
                    fallback_text=room_name,
                )

    if max_guests == 2:
        parsed_guests = _extract_max_guests(raw_text)
        if parsed_guests:
            max_guests = parsed_guests

    if not bed_config:
        bed_config = _extract_bed_config(raw_text)

    if not amenities:
        amenities = _extract_amenities(soup, raw_text)

    if not images:
        images = _extract_images_from_embedded(raw_text)

    if not room_type:
        room_type = _infer_room_type(
            json_ld_type=json_ld_type,
            name=name,
            description=description,
        )

    if not name:
        return None

    return ScrapedBookingListing(
        name=name,
        type=room_type,
        description=description,
        images=images[:20],
        price_per_night=price if price and price > 0 else 0,
        currency_code=currency_code,
        max_guests=max_guests,
        bed_config=bed_config,
        amenities=amenities,
    )


async def _parse_with_llm(html: str) -> ScrapedBookingListing | None:
    """Use LLM to extract listing data when static parsing fails."""
    if OpenAI is None:
        return None

    settings = get_settings()
    if not settings.openai_api_key:
        return None

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "svg", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)[:12000]

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.agent_model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a data extraction assistant. Extract Booking.com listing details "
                        "from the provided text content. Return a JSON object with these fields:\n"
                        '- "name" (string, listing title)\n'
                        '- "type" (string, e.g. "Apartment", "Suite", "Villa", "Hotel Room")\n'
                        '- "description" (string, listing description)\n'
                        '- "images" (array of image URL strings, empty array if none found)\n'
                        '- "price_per_night" (number, nightly price in the listed currency, 0 if not found)\n'
                        '- "currency_code" (string, 3-letter ISO currency code, "USD" if not found)\n'
                        '- "max_guests" (integer, maximum guests, 2 if not found)\n'
                        '- "bed_config" (string, e.g. "1 King Bed + 1 Sofa Bed")\n'
                        '- "amenities" (array of strings)\n'
                        "Extract only what you can find. Do not fabricate data."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Extract Booking.com listing details from this content:\n\n{text}",
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

        parsed_currency = _parse_currency_code(data.get("currency_code")) or "USD"

        return ScrapedBookingListing(
            name=data["name"],
            type=data.get("type", "Apartment"),
            description=data.get("description", ""),
            images=[
                value
                for value in data.get("images", [])
                if isinstance(value, str) and value.startswith("http")
            ],
            price_per_night=price,
            currency_code=parsed_currency,
            max_guests=int(data.get("max_guests", 2)),
            bed_config=data.get("bed_config", ""),
            amenities=[item for item in data.get("amenities", []) if isinstance(item, str)],
        )
    except Exception as exc:
        logger.warning("Booking.com LLM extraction failed: %s", exc)
        return None


async def scrape_booking_listing(url: str) -> ScrapedBookingListing:
    """Scrape a Booking.com listing URL and return structured data."""
    canonical_url = validate_booking_url(url)

    try:
        html = await fetch_booking_page(canonical_url)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            raise ValueError("Booking.com blocked this request. Please try again later.")
        if exc.response.status_code == 404:
            raise ValueError("Booking.com listing not found. Please check the URL.")
        raise ValueError(f"Failed to fetch Booking.com page: {exc.response.status_code}")
    except httpx.TimeoutException:
        raise ValueError("Request to Booking.com timed out. Please try again.")
    except httpx.RequestError as exc:
        raise ValueError(f"Could not connect to Booking.com: {exc}")

    static_listing = _parse_static(html)
    if static_listing and static_listing.price_per_night > 0:
        logger.info("Booking.com static parsing succeeded for %s", canonical_url)
        return static_listing

    llm_listing = await _parse_with_llm(html)

    if static_listing and llm_listing:
        logger.info("Merging Booking.com static + LLM data for %s", canonical_url)
        merged_currency = static_listing.currency_code
        if merged_currency == "USD" and llm_listing.currency_code:
            merged_currency = llm_listing.currency_code

        return ScrapedBookingListing(
            name=static_listing.name,
            type=static_listing.type,
            description=static_listing.description,
            images=static_listing.images or llm_listing.images,
            price_per_night=llm_listing.price_per_night,
            currency_code=merged_currency,
            max_guests=static_listing.max_guests,
            bed_config=static_listing.bed_config or llm_listing.bed_config,
            amenities=static_listing.amenities or llm_listing.amenities,
        )

    if llm_listing:
        logger.info("Booking.com LLM extraction succeeded for %s", canonical_url)
        return llm_listing

    if static_listing:
        logger.info("Booking.com static parsing succeeded (no price) for %s", canonical_url)
        return static_listing

    raise ValueError(
        "Could not extract listing details from this Booking.com page. "
        "The page may require JavaScript rendering, or the listing may be unavailable."
    )
