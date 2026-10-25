from django import template

from tracker.models import Application

register = template.Library()


@register.filter
def status_label(value):
    """Human label for a raw Application status value ("no_response" → "No response")."""
    try:
        return Application.Status(value).label
    except ValueError:
        return value
