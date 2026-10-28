import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import translation

from accounts.factories import UserFactory
from tracker.factories import ApplicationFactory, CompanyFactory, EventFactory, VacancyFactory
from tracker.models import Application

pytestmark = pytest.mark.django_db

# Labels every main page shows in English today. The fixture data below uses
# words that cannot contain any of them, so a hit is always an untranslated label.
ENGLISH_LABELS = [
    "Dashboard",
    "Inbox",
    "Applications",
    "Vacancies",
    "Companies",
    "Log out",
    "Needs attention",
    "I applied",
    "Dismiss",
    "Timeline",
    "Change status",
    "Add event",
    "Attachments",
    "Log in",
    "Save",
]


@pytest.fixture
def application(client):
    user = UserFactory(username="olga")
    company = CompanyFactory(owner=user, name="Ľubovoľná")
    VacancyFactory(company=company, title="Тестовая позиция", score=80)
    application = ApplicationFactory(vacancy__company=company, vacancy__title="Другая позиция")
    EventFactory(application=application, text="звонок")
    client.force_login(user)
    return application


def page_urls(application):
    return {
        "dashboard": reverse("tracker:dashboard"),
        "inbox": reverse("tracker:inbox"),
        "applications": reverse("tracker:application_list"),
        "application": application.get_absolute_url(),
        "vacancy_form": reverse("tracker:vacancy_add"),
        "companies": reverse("tracker:company_list"),
    }


@pytest.mark.parametrize("language", ["sk", "ru"])
@pytest.mark.parametrize(
    "page", ["dashboard", "inbox", "applications", "application", "vacancy_form", "companies"]
)
def test_main_pages_have_no_english_labels(client, application, language, page):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language

    html = client.get(page_urls(application)[page]).text

    assert [label for label in ENGLISH_LABELS if label in html] == []


@pytest.mark.parametrize("language", ["sk", "ru"])
def test_login_page_has_no_english_labels(client, language):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language

    html = client.get(reverse("login")).text

    assert [label for label in ENGLISH_LABELS if label in html] == []


def test_status_labels_are_translated():
    with translation.override("ru"):
        assert str(Application.Status.NO_RESPONSE.label) == "Нет ответа"
