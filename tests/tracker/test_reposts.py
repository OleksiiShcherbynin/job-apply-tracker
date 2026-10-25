from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertContains, assertNotContains

from accounts.factories import UserFactory
from tracker.factories import ApplicationFactory, VacancyFactory
from tracker.models import Application, Vacancy

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(client):
    user = UserFactory()
    client.force_login(user)
    return user


@pytest.fixture(autouse=True)
def media_in_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def earlier_application(
    user, status="applied", applied_at=date(2026, 10, 1), title="Junior Dev", company="Softec"
):
    return ApplicationFactory(
        vacancy__company__owner=user,
        vacancy__company__name=company,
        vacancy__title=title,
        vacancy__state=Vacancy.State.APPLIED,
        status=status,
        applied_at=applied_at,
    )


def repost(user, earlier_vacancy, **kwargs):
    return VacancyFactory(
        company=earlier_vacancy.company,
        title=earlier_vacancy.title,
        first_seen_at=timezone.now() - timedelta(hours=1),
        **kwargs,
    )


def test_inbox_marks_vacancy_already_applied(client, user):
    earlier = earlier_application(user, status="rejected")
    repost(user, earlier.vacancy)
    response = client.get(reverse("tracker:inbox"))
    assertContains(response, "Already applied on 2026-10-01 — Rejected")
    assertContains(response, earlier.get_absolute_url())


def test_inbox_marks_vacancy_dismissed_before(client, user):
    old = VacancyFactory(
        company__owner=user,
        company__name="Softec",
        title="Junior Dev",
        state=Vacancy.State.DISMISSED,
        dismiss_reason="Senior only",
    )
    repost(user, old)
    response = client.get(reverse("tracker:inbox"))
    assertContains(response, "Dismissed before: Senior only")


def test_markers_ignore_other_owners(client, user):
    stranger_application = earlier_application(UserFactory())
    VacancyFactory(company__owner=user, company__name="Softec", title="Junior Dev")
    response = client.get(reverse("tracker:inbox"))
    assertNotContains(response, "Already applied")
    assert stranger_application.pk  # sanity: the other owner's application exists


def test_first_apply_needs_no_confirmation(client, user):
    vacancy = VacancyFactory(company__owner=user)
    url = reverse("tracker:vacancy_apply", args=[vacancy.pk])
    assertNotContains(client.get(url), 'name="apply_again"')
    client.post(url, {"applied_at": "2026-10-20"})
    assert Application.objects.filter(vacancy=vacancy).exists()


def test_apply_requires_confirmation_when_previous_exists(client, user):
    earlier = earlier_application(user)
    new = repost(user, earlier.vacancy)
    url = reverse("tracker:vacancy_apply", args=[new.pk])
    page = client.get(url)
    assertContains(page, "You already applied")
    assertContains(page, 'name="apply_again"')
    response = client.post(url, {"applied_at": "2026-10-20"})
    assert response.status_code == 200
    assert not Application.objects.filter(vacancy=new).exists()


def test_apply_again_links_previous_attempt(client, user):
    older = earlier_application(user, applied_at=date(2026, 9, 1))
    latest = ApplicationFactory(
        vacancy__company=older.vacancy.company,
        vacancy__title="Junior Dev",
        vacancy__state=Vacancy.State.APPLIED,
        applied_at=date(2026, 10, 1),
    )
    new = repost(user, latest.vacancy)
    url = reverse("tracker:vacancy_apply", args=[new.pk])
    client.post(url, {"applied_at": "2026-10-20", "apply_again": "on"})
    application = Application.objects.get(vacancy=new)
    assert application.previous_attempt == latest
    assert older.later_attempts.count() == 0


def test_detail_shows_previous_and_later_links(client, user):
    earlier = earlier_application(user)
    new = repost(user, earlier.vacancy)
    later = new.mark_applied(date(2026, 10, 20), previous_attempt=earlier)

    newer_page = client.get(later.get_absolute_url())
    assertContains(newer_page, "Previous attempt")
    assertContains(newer_page, earlier.get_absolute_url())

    earlier_page = client.get(earlier.get_absolute_url())
    assertContains(earlier_page, "Later attempt")
    assertContains(earlier_page, later.get_absolute_url())


def test_inbox_num_queries_with_markers(client, user, django_assert_num_queries):
    for n in range(3):
        earlier = earlier_application(user, title=f"Job {n}", company=f"Company {n}")
        repost(user, earlier.vacancy)
    with django_assert_num_queries(3):
        client.get(reverse("tracker:inbox"), {"unprocessed": "1", "low": "1"})
