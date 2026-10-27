from django import template

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


@register.filter
def status_label(value):
    """Human label for a raw Application status value ("no_response" → "No response")."""
    try:
        return Application.Status(value).label
    except ValueError:
        return value
