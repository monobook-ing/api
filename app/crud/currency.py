from __future__ import annotations

from collections.abc import Iterable

from supabase import Client

DEFAULT_CURRENCY_CODE = "USD"
DEFAULT_CURRENCY_DISPLAY = "$"


def normalize_currency_code(value: str | None) -> str:
    if not value:
        return DEFAULT_CURRENCY_CODE

    normalized = value.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        return DEFAULT_CURRENCY_CODE
    return normalized


def resolve_currency_display(code: str, display_map: dict[str, str]) -> str:
    if code in display_map:
        return display_map[code]
    if code == DEFAULT_CURRENCY_CODE:
        return DEFAULT_CURRENCY_DISPLAY
    return code


async def get_currency_display_map(
    client: Client,
    codes: Iterable[str | None],
) -> dict[str, str]:
    normalized_codes = sorted(
        {normalize_currency_code(code) for code in codes if code is not None}
    )
    if not normalized_codes:
        return {}

    response = (
        client.table("currencies")
        .select("code, display")
        .in_("code", normalized_codes)
        .execute()
    )

    result: dict[str, str] = {}
    for row in response.data or []:
        code = normalize_currency_code(row.get("code"))
        display = row.get("display")
        if isinstance(display, str) and display.strip():
            result[code] = display.strip()
        else:
            result[code] = code
    return result

