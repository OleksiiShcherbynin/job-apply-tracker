from datetime import timedelta

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertContains, assertNotContains

from accounts.factories import UserFactory
from tracker.factories import ApplicationFactory, VacancyFactory
from tracker.models import Vacancy

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(client):
    user = UserFactory()
    client.force_login(user)
    return user


def days_ago(n):
    return timezone.now() - timedelta(days=n)


def vacancy(user, **kwargs):
    return VacancyFactory(company__owner=user, **kwargs)


def ids(queryset):
    return set(queryset.values_list("pk", flat=True))


def views(user):
    qs = Vacancy.objects
    return {
        "default": ids(qs.for_inbox_view(user)),
        "unprocessed": ids(qs.for_inbox_view(user, default=False, unprocessed=True)),
        "low": ids(qs.for_inbox_view(user, default=False, below_threshold=True)),
    }


def test_default_shows_fresh_scored_and_manual(user):
    scored = vacancy(user, score=70, first_seen_at=days_ago(1))
    manual = vacancy(user)  # no score, created now
    assert views(user)["default"] == {scored.pk, manual.pk}


def test_boundaries_score_40_and_age_exactly_fresh_days_are_default(user):
    # Review Focus #4: 40 is "40+", and day 5 still counts as fresh.
    edge = vacancy(user, score=40, first_seen_at=days_ago(5) + timedelta(seconds=30))
    assert edge.pk in views(user)["default"]


def test_old_vacancy_moves_to_unprocessed(user):
    old_scored = vacancy(user, score=80, first_seen_at=days_ago(6))
    old_manual = vacancy(user)
    Vacancy.objects.filter(pk=old_manual.pk).update(created_at=days_ago(9))
    result = views(user)
    assert {old_scored.pk, old_manual.pk} <= result["unprocessed"]
    assert not {old_scored.pk, old_manual.pk} & result["default"]


def test_dismissed_40_plus_in_unprocessed_low_in_below_threshold(user):
    high = vacancy(user, score=60, state=Vacancy.State.DISMISSED, dismiss_reason="Senior")
    low = vacancy(user, score=20, state=Vacancy.State.DISMISSED)
    result = views(user)
    assert high.pk in result["unprocessed"]
    assert low.pk in result["low"]
    assert not {high.pk, low.pk} & result["default"]


def test_only_newest_repost_in_default(user):
    original = vacancy(
        user, company__name="Softec", title="Junior Dev", score=70, first_seen_at=days_ago(3)
    )
    repost = VacancyFactory(
        company=original.company, title="Junior Dev", score=70, first_seen_at=days_ago(1)
    )
    result = views(user)
    assert repost.pk in result["default"]
    assert original.pk in result["unprocessed"]
    flags = dict(
        Vacancy.objects.for_inbox_view(user, unprocessed=True).values_list("pk", "has_newer_repost")
    )
    assert flags == {repost.pk: False, original.pk: True}


def test_every_unapplied_vacancy_in_exactly_one_view(user):
    made = [
        vacancy(user, score=90, first_seen_at=days_ago(1)),  # default
        vacancy(user),  # manual, fresh: default
        vacancy(user, score=90, first_seen_at=days_ago(20)),  # old: unprocessed
        vacancy(user, score=90, state=Vacancy.State.DISMISSED),  # unprocessed
        vacancy(user, score=10, first_seen_at=days_ago(1)),  # low
        vacancy(user, score=10, state=Vacancy.State.DISMISSED),  # low
    ]
    ApplicationFactory(vacancy__company__owner=user, vacancy__state=Vacancy.State.APPLIED)
    result = views(user)
    sets = list(result.values())
    assert sum(len(s) for s in sets) == len(set().union(*sets))  # disjoint
    assert set().union(*sets) == {v.pk for v in made}  # covers every unapplied one


def test_user_threshold_setting_respected(user):
    user.inbox_min_score = 70
    user.save()
    mid = vacancy(user, score=55, first_seen_at=days_ago(1))
    result = views(user)
    assert mid.pk in result["low"]
    assert mid.pk not in result["default"]


def test_toggles_via_get_params(client, user):
    vacancy(user, title="Fresh one", score=80, first_seen_at=days_ago(1))
    vacancy(user, title="Old one", score=80, first_seen_at=days_ago(30))
    vacancy(user, title="Weak one", score=15, first_seen_at=days_ago(1))
    url = reverse("tracker:inbox")

    plain = client.get(url)
    assertContains(plain, "Fresh one")
    assertNotContains(plain, "Old one")
    assertNotContains(plain, "Weak one")

    everything = client.get(url, {"unprocessed": "1", "low": "1"})
    for title in ("Fresh one", "Old one", "Weak one"):
        assertContains(everything, title)


def test_card_shows_russian_reasons_and_rough_marker(client, user):
    vacancy(
        user,
        score=70,
        score_stage=Vacancy.ScoreStage.ROUGH,
        score_reasons="English reason",
        score_reasons_ru="Русская причина",
    )
    # Reasons follow the interface language (Stage 4); Russian needs the Russian UI.
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "ru"
    response = client.get(reverse("tracker:inbox"))
    assertContains(response, "Русская причина")
    assertNotContains(response, "English reason")
    assertContains(response, "черновая")  # the "rough" marker, translated


def test_restore_returns_dismissed_to_inbox(client, user):
    dismissed = vacancy(user, state=Vacancy.State.DISMISSED, dismiss_reason="Nope")
    response = client.post(reverse("tracker:vacancy_restore", args=[dismissed.pk]))
    assert response.status_code == 302
    dismissed.refresh_from_db()
    assert dismissed.state == Vacancy.State.INBOX
    assert dismissed.dismiss_reason == ""


def test_restore_is_post_only(client, user):
    dismissed = vacancy(user, state=Vacancy.State.DISMISSED)
    url = reverse("tracker:vacancy_restore", args=[dismissed.pk])
    assert client.get(url).status_code == 405


def test_foreign_vacancy_restore_404(client, user):
    foreign = VacancyFactory(state=Vacancy.State.DISMISSED)
    response = client.post(reverse("tracker:vacancy_restore", args=[foreign.pk]))
    assert response.status_code == 404


def test_restore_ignores_applied_vacancy(client, user):
    application = ApplicationFactory(
        vacancy__company__owner=user, vacancy__state=Vacancy.State.APPLIED
    )
    url = reverse("tracker:vacancy_restore", args=[application.vacancy.pk])
    assert client.post(url).status_code == 404


def test_dismiss_ignores_applied_vacancy(client, user):
    application = ApplicationFactory(
        vacancy__company__owner=user, vacancy__state=Vacancy.State.APPLIED
    )
    url = reverse("tracker:vacancy_dismiss", args=[application.vacancy.pk])
    assert client.post(url).status_code == 404
    application.vacancy.refresh_from_db()
    assert application.vacancy.state == Vacancy.State.APPLIED


def test_inbox_num_queries_with_toggles(client, user, django_assert_num_queries):
    for n in range(4):
        vacancy(user, score=30 + n * 20, first_seen_at=days_ago(n * 3))
    vacancy(user, score=80, state=Vacancy.State.DISMISSED)
    with django_assert_num_queries(3):
        client.get(reverse("tracker:inbox"), {"unprocessed": "1", "low": "1"})


def test_dismiss_returns_to_the_same_toggles(client, user):
    # Found in final review: working through "Unprocessed" lost the toggles
    # after every click.
    old = vacancy(user, score=80, first_seen_at=days_ago(20))
    response = client.post(
        reverse("tracker:vacancy_dismiss", args=[old.pk]), {"next": "/inbox/?unprocessed=1"}
    )
    assert response.url == "/inbox/?unprocessed=1"


def test_restore_returns_to_the_same_toggles(client, user):
    dismissed = vacancy(user, state=Vacancy.State.DISMISSED)
    response = client.post(
        reverse("tracker:vacancy_restore", args=[dismissed.pk]), {"next": "/inbox/?unprocessed=1"}
    )
    assert response.url == "/inbox/?unprocessed=1"


def test_foreign_next_url_is_ignored(client, user):
    dismissed = vacancy(user, state=Vacancy.State.DISMISSED)
    response = client.post(
        reverse("tracker:vacancy_restore", args=[dismissed.pk]), {"next": "https://evil.example/"}
    )
    assert response.url == reverse("tracker:inbox")


def test_inbox_forms_carry_current_toggles(client, user):
    vacancy(user, score=80, first_seen_at=days_ago(20))
    response = client.get(reverse("tracker:inbox"), {"unprocessed": "1"})
    assertContains(response, 'name="next" value="/inbox/?unprocessed=1"')
