from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertContains, assertNotContains

from accounts.factories import UserFactory
from tracker.factories import ApplicationFactory, EventFactory, VacancyFactory
from tracker.models import Application

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(client):
    user = UserFactory()
    client.force_login(user)
    return user


def days_ago(n):
    return timezone.now() - timedelta(days=n)


def test_dashboard_shows_stale_application(client, user):
    stale = ApplicationFactory(
        vacancy__company__owner=user,
        vacancy__title="Silent company job",
        applied_at=days_ago(10).date(),
    )
    EventFactory(application=stale, happened_at=days_ago(10))
    fresh = ApplicationFactory(vacancy__company__owner=user, vacancy__title="Fresh job")
    EventFactory(application=fresh, happened_at=days_ago(1))

    response = client.get(reverse("tracker:dashboard"))
    needs_attention = list(response.context["needs_attention"])
    assert needs_attention == [stale]
    assertContains(response, "Silent company job")


def test_dashboard_ignores_other_users(client, user):
    ApplicationFactory(vacancy__title="Stranger's stale job", applied_at=days_ago(30).date())
    response = client.get(reverse("tracker:dashboard"))
    assert list(response.context["needs_attention"]) == []
    assertNotContains(response, "Stranger")


def test_status_counts(client, user):
    ApplicationFactory.create_batch(2, vacancy__company__owner=user)
    ApplicationFactory(vacancy__company__owner=user, status=Application.Status.INTERVIEW)
    ApplicationFactory(status=Application.Status.INTERVIEW)  # чужой, не считается
    response = client.get(reverse("tracker:dashboard"))
    counts = dict(response.context["status_counts"])
    assert counts["Applied"] == 2
    assert counts["Interview"] == 1
    assert counts["Offer"] == 0


def test_inbox_count(client, user):
    VacancyFactory.create_batch(3, company__owner=user)
    VacancyFactory()  # чужая
    response = client.get(reverse("tracker:dashboard"))
    assert response.context["inbox_count"] == 3


def test_dashboard_num_queries(client, user, django_assert_num_queries):
    for _ in range(4):
        application = ApplicationFactory(
            vacancy__company__owner=user, applied_at=days_ago(20).date()
        )
        EventFactory.create_batch(2, application=application, happened_at=days_ago(20))
    # Сессия + пользователь + needs_attention + счётчики статусов
    # + последние события + число во входящих.
    with django_assert_num_queries(6):
        client.get(reverse("tracker:dashboard"))


def test_inbox_count_counts_default_view_only(client, user):
    VacancyFactory(company__owner=user, score=80)  # default
    VacancyFactory(company__owner=user, score=10)  # below threshold
    VacancyFactory(company__owner=user, score=80, first_seen_at=days_ago(30))  # old
    response = client.get(reverse("tracker:dashboard"))
    assert response.context["inbox_count"] == 1
