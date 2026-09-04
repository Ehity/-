"""Deterministic service-name normalization for the MVP."""

import re


_KNOWN_SERVICES = (
    (("NETFLIX",), "Netflix"),
    (("YANDEX*PLUS", "YM*PLUS", "ЯНДЕКС ПЛЮС"), "Яндекс Плюс"),
    (("VK MUSIC", "ВК МУЗЫКА"), "VK Музыка"),
    (("GOOGLE*YOUTUBE", "YOUTUBE PREMIUM"), "YouTube Premium"),
    (("SPOTIFY",), "Spotify"),
    (("KINOPOISK", "КИНОПОИСК"), "Кинопоиск"),
)


def normalize_service_name(raw_name: str) -> str:
    """Return a known service name or a cleaned version of the original name."""
    if not isinstance(raw_name, str):
        return ""

    cleaned = " ".join(raw_name.strip().split())
    if not cleaned:
        return ""

    uppercase_name = cleaned.upper()
    for markers, service_name in _KNOWN_SERVICES:
        if any(marker in uppercase_name for marker in markers):
            return service_name

    # Remove only obvious transaction noise for unknown services.
    return re.sub(r"\s+", " ", cleaned).strip()
