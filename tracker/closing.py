"""What it means for the author's data that a Profesia posting has closed.

job-ai-assist reports closures; the rules live here:
- an application still at Applied counts as silence and moves to No response
  (even when the company reposted the vacancy under a new offer id);
- any other application keeps its status (the company already answered) and
  gets a note in its timeline;
- an undecided inbox vacancy is dismissed; a dismissed one keeps its reason;
- every closure is recorded once: a repeated report changes nothing.
"""

from django.db import transaction

from .models import Application, ApplicationEvent, Vacancy

CLOSED_EVENT_TEXT = "Posting closed on Profesia"
CLOSED_DISMISS_REASON = "Closed on Profesia"


def report_closed(owner, external_id: str, seen_at) -> str:
    """Apply one closure report. Returns "closed", "unchanged" or "unknown"."""
    with transaction.atomic():
        # The row lock makes a report repeated in parallel wait and see closed_at.
        vacancy = (
            Vacancy.objects.select_for_update()
            .filter(owner=owner, external_id=external_id)
            .first()
        )
        if vacancy is None:
            return "unknown"
        if vacancy.closed_at is not None:
            return "unchanged"

        vacancy.closed_at = seen_at
        changed = ["closed_at", "updated_at"]
        application = Application.objects.filter(vacancy=vacancy).first()
        if application is not None:
            _close_application(application, seen_at)
        elif vacancy.state == Vacancy.State.INBOX:
            vacancy.state = Vacancy.State.DISMISSED
            vacancy.dismiss_reason = CLOSED_DISMISS_REASON
            changed += ["state", "dismiss_reason"]
        vacancy.save(update_fields=changed)
        return "closed"


def _close_application(application: Application, seen_at) -> None:
    if application.status == Application.Status.APPLIED:
        application.change_status(
            Application.Status.NO_RESPONSE, comment=CLOSED_EVENT_TEXT, when=seen_at
        )
    else:
        ApplicationEvent.objects.create(
            application=application,
            type=ApplicationEvent.EventType.NOTE,
            happened_at=seen_at,
            text=CLOSED_EVENT_TEXT,
        )
