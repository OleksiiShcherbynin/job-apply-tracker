"""What the tracker knows about Profesia links."""

import re
from urllib.parse import urlsplit

_HOSTS = {"profesia.sk", "www.profesia.sk"}
_OFFER_ID = re.compile(r"O\d+")


def profesia_offer_id(url: str) -> str | None:
    """The offer id (``O1234567``) of a Profesia posting link, or None.

    Only the last path segment counts, so company and search pages, and
    look-alike paths on other sites, give None.
    """
    try:
        parts = urlsplit(url)
    except ValueError:  # e.g. a broken IPv6 host; never block a save or a migration
        return None
    if parts.hostname not in _HOSTS:
        return None
    segments = [segment for segment in parts.path.split("/") if segment]
    if segments and _OFFER_ID.fullmatch(segments[-1]):
        return segments[-1]
    return None
