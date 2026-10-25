"""Identity of a posting independent of its offer id.

Employers repost the same vacancy under a new id; company + title is what stays.
The rule must match job-ai-assist's app/store.py::fingerprint exactly, so both
systems agree on what "the same vacancy" means.
"""

import unicodedata


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(without_accents.split())


def fingerprint(company: str, title: str) -> str:
    return f"{_normalize(company or '')}|{_normalize(title or '')}"
