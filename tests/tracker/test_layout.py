import re
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.urls import reverse

from accounts.factories import UserFactory
from tracker.factories import ApplicationFactory, CompanyFactory
from tracker.templatetags.tracker_extras import nav_section

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(client):
    user = UserFactory()
    client.force_login(user)
    return user


def test_header_has_brand_and_language_dropdown(client, user):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "ru"

    html = client.get(reverse("tracker:dashboard")).text

    assert re.search(r'class="brand"[^>]*>\s*Job Apply Tracker\s*<', html)
    assert '<select name="language"' in html
    for code, label in [("en", "EN"), ("sk", "SK"), ("ru", "RU")]:
        assert re.search(rf'value="{code}"[^>]*>{label}</option>', html)
    assert re.search(r'value="ru" selected', html)
    assert not re.search(r'value="en" selected', html)


@pytest.mark.parametrize(
    "page",
    ["dashboard", "inbox", "application_detail", "vacancy_list", "company_list"],
)
def test_current_section_is_marked(client, user, page):
    nav_url = {
        "dashboard": reverse("tracker:dashboard"),
        "inbox": reverse("tracker:inbox"),
        "application_detail": reverse("tracker:application_list"),
        "vacancy_list": reverse("tracker:vacancy_list"),
        "company_list": reverse("tracker:company_list"),
    }[page]
    if page == "application_detail":
        application = ApplicationFactory(vacancy__company=CompanyFactory(owner=user))
        url = application.get_absolute_url()
    else:
        url = nav_url

    html = client.get(url).text

    assert html.count('aria-current="page"') == 1
    assert re.search(rf'href="{re.escape(nav_url)}"[^>]*aria-current="page"', html)


@pytest.mark.parametrize(
    ("url_name", "section"),
    [
        ("dashboard", "dashboard"),
        ("inbox", "inbox"),
        ("vacancy_apply", "inbox"),
        ("vacancy_dismiss", "inbox"),
        ("vacancy_restore", "inbox"),
        ("application_list", "applications"),
        ("application_detail", "applications"),
        ("application_add_event", "applications"),
        ("application_change_status", "applications"),
        ("application_add_attachment", "applications"),
        ("attachment_download", "applications"),
        ("vacancy_list", "vacancies"),
        ("vacancy_add", "vacancies"),
        ("vacancy_edit", "vacancies"),
        ("vacancy_delete", "vacancies"),
        ("company_list", "companies"),
        ("company_add", "companies"),
        ("company_edit", "companies"),
        ("company_delete", "companies"),
        ("login", ""),
    ],
)
def test_nav_section_mapping(url_name, section):
    request = SimpleNamespace(resolver_match=SimpleNamespace(url_name=url_name))

    assert nav_section(request) == section


def test_nav_section_without_a_resolved_url():
    assert nav_section(SimpleNamespace(resolver_match=None)) == ""


def test_theme_css_is_linked(client, user):
    html = client.get(reverse("tracker:dashboard")).text

    assert "css/pico.min.css" in html
    assert html.index("css/pico.min.css") < html.index("css/theme.css")


def test_login_page_uses_the_theme_without_nav(client):
    html = client.get(reverse("login")).text

    assert 'class="brand"' in html
    assert '<select name="language"' in html
    assert 'class="pill"' not in html
    assert reverse("tracker:inbox") not in html
