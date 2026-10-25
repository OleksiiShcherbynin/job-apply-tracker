"""Turning one vacancy pushed by job-ai-assist into a tracker row.

The rules protect the author's decisions: a push may refresh what job-ai-assist
owns (title, link, salary, score, reasons) but never the state, the dismissal,
the company link or the application.
"""

from django.db import transaction

from .fingerprints import fingerprint
from .models import Company, Vacancy

UNKNOWN_COMPANY = "Unknown company"

# Fields job-ai-assist owns and may refresh on every push.
_REFRESHED = ("title", "url", "location", "salary", "score", "score_stage")


def ingest_vacancy(owner, data: dict) -> tuple[Vacancy, str]:
    """Create, update or adopt the owner's vacancy for one validated item.

    Returns the vacancy and "created" or "updated" (adoption counts as updated).
    """
    with transaction.atomic():
        known = Vacancy.objects.filter(owner=owner, external_id=data["external_id"]).first()
        if known is not None:
            _refresh(known, data)
            known.save()
            return known, "updated"

        company_name = (data.get("company") or "").strip() or UNKNOWN_COMPANY
        manual = _matching_manual_vacancy(owner, company_name, data["title"])
        if manual is not None:
            _adopt(manual, data)
            manual.save()
            return manual, "updated"

        vacancy = Vacancy(
            owner=owner,
            company=_company(owner, company_name),
            source=Vacancy.Source.JOB_AI_ASSIST,
            external_id=data["external_id"],
            first_seen_at=data.get("first_seen_at"),
        )
        _refresh(vacancy, data)
        vacancy.save()
        return vacancy, "created"


def _refresh(vacancy: Vacancy, data: dict) -> None:
    for field in _REFRESHED:
        if field in data:
            setattr(vacancy, field, data[field])
    _set_reasons(vacancy, data)


def _adopt(vacancy: Vacancy, data: dict) -> None:
    # A row the author typed in before Stage 2: link it to the offer and add the
    # scoring, but keep everything the author entered.
    vacancy.external_id = data["external_id"]
    vacancy.score = data["score"]
    vacancy.score_stage = data["score_stage"]
    vacancy.first_seen_at = data.get("first_seen_at")
    for field in ("location", "salary"):
        if not getattr(vacancy, field) and data.get(field):
            setattr(vacancy, field, data[field])
    _set_reasons(vacancy, data)


def _set_reasons(vacancy: Vacancy, data: dict) -> None:
    # An omitted key means "no news about reasons" and keeps what is stored.
    if "reasons_en" in data:
        vacancy.score_reasons = "\n".join(data["reasons_en"])
    if "reasons_ru" in data:
        vacancy.score_reasons_ru = "\n".join(data["reasons_ru"])


def _matching_manual_vacancy(owner, company_name: str, title: str) -> Vacancy | None:
    return (
        Vacancy.objects.filter(
            owner=owner,
            external_id__isnull=True,
            fingerprint=fingerprint(company_name, title),
        )
        .order_by("-created_at")
        .first()
    )


def _company(owner, name: str) -> Company:
    existing = Company.objects.filter(owner=owner, name__iexact=name).first()
    return existing or Company.objects.create(owner=owner, name=name)
