from datetime import UTC, datetime

import pytest
from django.urls import reverse

from accounts.factories import UserFactory
from tracker.closing import report_closed
from tracker.factories import ApplicationFactory, VacancyFactory
from tracker.models import Application, ApplicationEvent, Vacancy

pytestmark = pytest.mark.django_db

SEEN = datetime(2026, 10, 27, 8, 20, tzinfo=UTC)


@pytest.fixture
def user():
    return UserFactory()


def offer(owner, external_id="O1", **kwargs):
    return VacancyFactory(company__owner=owner, external_id=external_id, **kwargs)


def application(owner, status=Application.Status.APPLIED, **vacancy_kwargs):
    vacancy = offer(owner, state=Vacancy.State.APPLIED, **vacancy_kwargs)
    return ApplicationFactory(vacancy=vacancy, status=status)


def test_applied_becomes_no_response(user):
    app = application(user)
    assert report_closed(user, "O1", SEEN) == "closed"
    app.refresh_from_db()
    assert app.status == Application.Status.NO_RESPONSE
    event = app.events.first()
    assert event.type == ApplicationEvent.EventType.STATUS_CHANGE
    assert event.happened_at == SEEN
    assert event.text == "Applied → No response. Posting closed on Profesia"
    assert app.vacancy.closed_at == SEEN


def test_applied_with_repost_still_becomes_no_response(user):
    app = application(user, title="Junior Python")
    offer(user, "O2", company=app.vacancy.company, title="Junior Python")
    report_closed(user, "O1", SEEN)
    app.refresh_from_db()
    assert app.status == Application.Status.NO_RESPONSE


@pytest.mark.parametrize("status", [Application.Status.INTERVIEW, Application.Status.REJECTED])
def test_other_statuses_get_a_note_only(user, status):
    app = application(user, status=status)
    assert report_closed(user, "O1", SEEN) == "closed"
    app.refresh_from_db()
    assert app.status == status
    (event,) = app.events.all()
    assert event.type == ApplicationEvent.EventType.NOTE
    assert event.text == "Posting closed on Profesia"
    assert event.happened_at == SEEN


def test_inbox_vacancy_is_dismissed(user):
    vacancy = offer(user)
    assert report_closed(user, "O1", SEEN) == "closed"
    vacancy.refresh_from_db()
    assert vacancy.state == Vacancy.State.DISMISSED
    assert vacancy.dismiss_reason == "Closed on Profesia"
    assert vacancy.closed_at == SEEN


def test_dismissed_vacancy_keeps_its_reason(user):
    vacancy = offer(user, state=Vacancy.State.DISMISSED, dismiss_reason="too far")
    assert report_closed(user, "O1", SEEN) == "closed"
    vacancy.refresh_from_db()
    assert vacancy.dismiss_reason == "too far"
    assert vacancy.closed_at == SEEN


def test_second_report_is_unchanged(user):
    app = application(user)
    assert report_closed(user, "O1", SEEN) == "closed"
    assert report_closed(user, "O1", datetime(2026, 10, 28, tzinfo=UTC)) == "unchanged"
    assert app.events.count() == 1
    app.vacancy.refresh_from_db()
    assert app.vacancy.closed_at == SEEN


def test_unknown_external_id(user):
    assert report_closed(user, "O404", SEEN) == "unknown"


def test_other_owners_offer_is_unknown(user):
    foreign = offer(UserFactory())
    assert report_closed(user, "O1", SEEN) == "unknown"
    foreign.refresh_from_db()
    assert foreign.closed_at is None
    assert foreign.state == Vacancy.State.INBOX


def test_restored_closed_vacancy_keeps_closed_at(client, user):
    vacancy = offer(user)
    report_closed(user, "O1", SEEN)
    client.force_login(user)
    client.post(reverse("tracker:vacancy_restore", args=[vacancy.pk]))
    vacancy.refresh_from_db()
    assert vacancy.state == Vacancy.State.INBOX
    assert vacancy.closed_at == SEEN
    assert vacancy not in Vacancy.objects.to_check(user)
