import re
from functools import cache

from django import template
from django.utils import translation
from django.utils.translation import gettext

from tracker.closing import CLOSED_DISMISS_REASON, CLOSED_EVENT_TEXT
from tracker.models import Application

register = template.Library()


# Pages that act on an inbox card keep the Inbox section highlighted.
_INBOX_PAGES = {"inbox", "vacancy_apply", "vacancy_dismiss", "vacancy_restore"}


@register.simple_tag
def nav_section(request):
    """Which header section the current page belongs to ("" when none)."""
    match = getattr(request, "resolver_match", None)
    name = (match.url_name if match else None) or ""
    if name == "dashboard":
        return "dashboard"
    if name in _INBOX_PAGES:
        return "inbox"
    if name.startswith("application_") or name == "attachment_download":
        return "applications"
    if name.startswith("vacancy_"):
        return "vacancies"
    if name.startswith("company_"):
        return "companies"
    return ""


# What the code writes into the timeline (see Application.change_status and
# applied_event_text): "Applied → Rejected. <comment>" and "→ Applied".
_FIRST_STATUS = re.compile(r"→ (?P<new>[^→]+)")
_TRANSITION = re.compile(r"(?P<old>[^→]+) → (?P<new>[^→.]+)\.(?: (?P<comment>.*))?", re.DOTALL)
_PHRASES = {CLOSED_EVENT_TEXT, CLOSED_DISMISS_REASON}


@cache
def _status_labels():
    """English status label → its lazy label, which renders in the active language."""
    with translation.override("en"):
        return {str(label): label for label in Application.Status.labels}


@register.filter
def system_text(value):
    """A text the code stored in English, shown in the reader's language.

    Only the exact shapes the code writes are recognised; anything a person
    typed (a comment, a note, a dismiss reason) is returned as stored.
    """
    if value in _PHRASES:
        return gettext(value)
    labels = _status_labels()
    match = _FIRST_STATUS.fullmatch(value)
    if match and match["new"] in labels:
        return f"→ {labels[match['new']]}"
    match = _TRANSITION.fullmatch(value)
    if match and match["old"] in labels and match["new"] in labels:
        text = f"{labels[match['old']]} → {labels[match['new']]}."
        comment = match["comment"]
        if comment:
            text += " " + (gettext(comment) if comment in _PHRASES else comment)
        return text
    return value


@register.filter
def reasons(vacancy):
    """Score reasons in the reader's language, falling back to the other one."""
    if (translation.get_language() or "").startswith("ru"):
        return vacancy.score_reasons_ru or vacancy.score_reasons
    return vacancy.score_reasons or vacancy.score_reasons_ru


@register.filter
def status_label(value):
    """Human label for a raw Application status value ("no_response" → "No response")."""
    try:
        return Application.Status(value).label
    except ValueError:
        return value
