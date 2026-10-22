from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.factories import UserFactory
from tracker.factories import ApplicationFactory, EventFactory, VacancyFactory
from tracker.models import Application, Vacancy

pytestmark = pytest.mark.django_db


def days_ago(n):
    return timezone.now() - timedelta(days=n)


def make_application(*, status=Application.Status.APPLIED, applied_days_ago=0, owner=None):
    kwargs = {"status": status, "applied_at": days_ago(applied_days_ago).date()}
    if owner is not None:
        kwargs["vacancy__company__owner"] = owner
    return ApplicationFactory(**kwargs)


def test_inbox_orders_by_score_desc_nulls_last():
    user = UserFactory()
    no_score = VacancyFactory(company__owner=user, score=None)
    mid = VacancyFactory(company__owner=user, score=50)
    top = VacancyFactory(company__owner=user, score=90)
    assert list(Vacancy.objects.for_owner(user).inbox()) == [top, mid, no_score]


def test_needs_attention_stale_application_included():
    application = make_application(applied_days_ago=10)
    EventFactory(application=application, happened_at=days_ago(10))
    result = Application.objects.needs_attention(application.owner)
    assert application in result


def test_fresh_application_excluded():
    application = make_application(applied_days_ago=10)
    EventFactory(application=application, happened_at=days_ago(1))
    assert application not in Application.objects.needs_attention(application.owner)


def test_terminal_status_excluded():
    application = make_application(status=Application.Status.REJECTED, applied_days_ago=30)
    EventFactory(application=application, happened_at=days_ago(20))
    assert application not in Application.objects.needs_attention(application.owner)


def test_no_events_falls_back_to_applied_at():
    application = make_application(applied_days_ago=10)  # ни одного события
    assert application in Application.objects.needs_attention(application.owner)


def test_respects_owner_follow_up_days():
    owner = UserFactory(follow_up_days=30)
    application = make_application(applied_days_ago=10, owner=owner)
    EventFactory(application=application, happened_at=days_ago(10))
    assert application not in Application.objects.needs_attention(owner)


def test_other_owner_excluded():
    stale = make_application(applied_days_ago=10)
    stranger = UserFactory()
    assert stale not in Application.objects.needs_attention(stranger)
