from datetime import UTC, datetime

import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains

from accounts.factories import UserFactory
from tracker.factories import ApplicationFactory, VacancyFactory
from tracker.models import Vacancy

pytestmark = pytest.mark.django_db

CLOSED = datetime(2026, 10, 27, 8, 20, tzinfo=UTC)


@pytest.fixture
def user(client):
    user = UserFactory()
    client.force_login(user)
    return user


def test_inbox_card_shows_closed_date(client, user):
    VacancyFactory(company__owner=user, state=Vacancy.State.DISMISSED, closed_at=CLOSED)
    response = client.get(reverse("tracker:inbox"), {"unprocessed": "1"})
    assertContains(response, "Closed on Profesia (2026-10-27)")


def test_inbox_card_without_closed_date_has_no_label(client, user):
    VacancyFactory(company__owner=user)
    assertNotContains(client.get(reverse("tracker:inbox")), "Closed on Profesia")


def test_application_page_shows_closed_date(client, user):
    application = ApplicationFactory(vacancy__company__owner=user, vacancy__closed_at=CLOSED)
    assertContains(client.get(application.get_absolute_url()), "Closed on Profesia (2026-10-27)")
