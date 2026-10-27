from datetime import date

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone, translation

from accounts.factories import UserFactory
from tracker.closing import CLOSED_DISMISS_REASON, CLOSED_EVENT_TEXT
from tracker.factories import ApplicationFactory, CompanyFactory, EventFactory, VacancyFactory
from tracker.models import Application, ApplicationEvent, Vacancy
from tracker.templatetags.tracker_extras import reasons, system_text

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("language", ["ru", "sk"])
def test_status_change_is_stored_in_english(language):
    application = ApplicationFactory()
    vacancy = VacancyFactory()

    with translation.override(language):
        application.change_status(Application.Status.REJECTED, comment="x")
        applied = vacancy.mark_applied(date(2026, 10, 20))

    texts = set(ApplicationEvent.objects.values_list("text", flat=True))
    assert texts == {"Applied → Rejected. x", "→ Applied"}
    assert applied.events.get().text == "→ Applied"


@pytest.mark.parametrize(
    ("stored", "shown"),
    [
        (
            "Applied → No response. Posting closed on Profesia",
            "Отправлена → Нет ответа. Объявление закрыто на Profesia",
        ),
        ("→ Applied", "→ Отправлена"),
        ("Applied → Rejected.", "Отправлена → Отказ."),
        ("Closed on Profesia", "Закрыто на Profesia"),
        ("Posting closed on Profesia", "Объявление закрыто на Profesia"),
        (
            "Applied → Interview. позвонить в пятницу",
            "Отправлена → Собеседование. позвонить в пятницу",
        ),
    ],
)
def test_system_text_translates_known_phrases(stored, shown):
    with translation.override("ru"):
        assert system_text(stored) == shown


@pytest.mark.parametrize(
    "stored",
    [
        "Applied → No response. Posting closed on Profesia",
        "→ Applied",
        "Applied → Rejected.",
        "Closed on Profesia",
        "Applied → Interview. call on Friday",
    ],
)
def test_system_text_in_english_is_unchanged(stored):
    with translation.override("en"):
        assert system_text(stored) == stored


@pytest.mark.parametrize(
    "stored",
    [
        "Foo → Bar.",
        "called them → no answer",
        "Applied → Applied → Rejected.",
        "→ Hired",
        "Applied → Rejected",  # no closing dot: not what change_status writes
        "",
    ],
)
def test_lookalike_text_is_left_alone(stored):
    with translation.override("ru"):
        assert system_text(stored) == stored


@pytest.mark.parametrize(
    ("en", "ru", "language", "expected"),
    [
        ("Python fits", "Python подходит", "ru", "Python подходит"),
        ("Python fits", "Python подходит", "en", "Python fits"),
        ("Python fits", "Python подходит", "sk", "Python fits"),
        ("Python fits", "", "ru", "Python fits"),
        ("", "Python подходит", "en", "Python подходит"),
        ("", "", "sk", ""),
    ],
)
def test_reasons_follow_language(en, ru, language, expected):
    vacancy = Vacancy(score_reasons=en, score_reasons_ru=ru)

    with translation.override(language):
        assert reasons(vacancy) == expected


@pytest.fixture
def user(client):
    user = UserFactory()
    client.force_login(user)
    return user


def test_timeline_shows_the_closure_in_the_users_language(client, user):
    application = ApplicationFactory(vacancy__company=CompanyFactory(owner=user))
    application.change_status(Application.Status.NO_RESPONSE, comment=CLOSED_EVENT_TEXT)
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "ru"

    html = client.get(application.get_absolute_url()).text

    assert "Отправлена → Нет ответа. Объявление закрыто на Profesia" in html
    assert "Posting closed on Profesia" not in html


def test_dashboard_recent_events_use_the_users_language(client, user):
    application = ApplicationFactory(vacancy__company=CompanyFactory(owner=user))
    EventFactory(application=application, text=CLOSED_EVENT_TEXT, happened_at=timezone.now())
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "ru"

    html = client.get(reverse("tracker:dashboard")).text

    assert "Объявление закрыто на Profesia" in html


def test_inbox_shows_the_closure_reason_in_the_users_language(client, user):
    VacancyFactory(
        company=CompanyFactory(owner=user),
        state=Vacancy.State.DISMISSED,
        dismiss_reason=CLOSED_DISMISS_REASON,
        score=90,
    )
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "ru"

    html = client.get(reverse("tracker:inbox"), {"unprocessed": "1"}).text

    assert "Закрыто на Profesia" in html
    assert CLOSED_DISMISS_REASON not in html


def test_inbox_card_shows_reasons_in_the_users_language(client, user):
    VacancyFactory(
        company=CompanyFactory(owner=user),
        score=90,
        score_reasons="Python fits",
        score_reasons_ru="Python подходит",
    )

    html = client.get(reverse("tracker:inbox")).text

    assert "Python fits" in html
    assert "Python подходит" not in html
