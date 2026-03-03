from __future__ import annotations

import pytest

from app.services.booking_scraper import _parse_static, validate_booking_url


def test_validate_booking_url_normalizes_to_canonical():
    url = (
        "booking.com/hotel/gb/cheval-three-quays.en-gb.html"
        "?aid=304142&label=test#availability"
    )
    assert (
        validate_booking_url(url)
        == "https://www.booking.com/hotel/gb/cheval-three-quays.en-gb.html"
    )


def test_validate_booking_url_rejects_non_booking_hosts():
    with pytest.raises(ValueError, match="Not a valid Booking.com listing URL"):
        validate_booking_url("https://example.com/hotel/gb/test.html")


def test_parse_static_extracts_required_listing_fields():
    html = """
    <html>
      <head>
        <meta property="og:title" content="Cheval Three Quays | Booking.com" />
        <meta property="og:description" content="Luxury aparthotel in London." />
        <meta property="og:image" content="https://cf.bstatic.com/xdata/images/hotel/max1024x768/100.jpg" />
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "Hotel",
            "name": "Cheval Three Quays",
            "description": "Spacious serviced apartments near Tower Bridge.",
            "image": [
              "https://cf.bstatic.com/xdata/images/hotel/max1024x768/200.jpg",
              "https://cf.bstatic.com/xdata/images/hotel/max1024x768/201.jpg"
            ],
            "offers": {
              "@type": "Offer",
              "price": "450",
              "priceCurrency": "GBP"
            },
            "amenityFeature": [
              {"@type": "LocationFeatureSpecification", "name": "Free WiFi"},
              {"@type": "LocationFeatureSpecification", "name": "Parking"}
            ]
          }
        </script>
        <script>
          window.__BOOTSTRAP__ = {
            "max_occupancy": 4,
            "bedroom_text": "1 large double bed and 1 sofa bed",
            "facility_name": "Airport shuttle"
          };
        </script>
      </head>
      <body>
        <ul data-testid="property-most-popular-facilities-wrapper">
          <li>Fitness center</li>
        </ul>
      </body>
    </html>
    """

    listing = _parse_static(html)
    assert listing is not None
    assert listing.name == "Cheval Three Quays"
    assert listing.type == "Apartment"
    assert listing.price_per_night == 450.0
    assert listing.currency_code == "GBP"
    assert listing.max_guests == 4
    assert "double bed" in listing.bed_config.lower()
    assert "Free WiFi" in listing.amenities
    assert len(listing.images) >= 1


def test_parse_static_defaults_to_usd_when_currency_missing():
    html = """
    <html>
      <head>
        <meta property="og:title" content="My Apartment | Booking.com" />
        <meta property="og:description" content="Simple apartment description." />
      </head>
      <body>
        2 guests
      </body>
    </html>
    """

    listing = _parse_static(html)
    assert listing is not None
    assert listing.currency_code == "USD"
    assert listing.name == "My Apartment"
    assert listing.max_guests == 2
