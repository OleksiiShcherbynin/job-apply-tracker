import importlib
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import Resolver404, clear_url_caches, resolve, reverse
from django.utils import timezone
from pytest_django.asserts import assertContains, assertNotContains

import config.urls
from accounts.factories import UserFactory
from tracker.factories import ApplicationFactory, AttachmentFactory, EventFactory
from tracker.models import Application, ApplicationEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(client):
    user = UserFactory()
    client.force_login(user)
    return user


@pytest.fixture(autouse=True)
def media_in_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def make_application(user, **kwargs):
    return ApplicationFactory(vacancy__company__owner=user, **kwargs)


# --- Список откликов ---


def test_list_shows_only_own(client, user):
    make_application(user, vacancy__title="My job")
    ApplicationFactory(vacancy__title="Not my job")
    response = client.get(reverse("tracker:application_list"))
    assertContains(response, "My job")
    assertNotContains(response, "Not my job")


def test_list_filters_by_status(client, user):
    make_application(user, vacancy__title="Waiting one")
    make_application(user, vacancy__title="Interview one", status=Application.Status.INTERVIEW)
    response = client.get(reverse("tracker:application_list"), {"status": "interview"})
    assertContains(response, "Interview one")
    assertNotContains(response, "Waiting one")


def test_search_by_company_name(client, user):
    make_application(user, vacancy__company__name="ESET")
    make_application(user, vacancy__company__name="Pantheon")
    response = client.get(reverse("tracker:application_list"), {"q": "eset"})
    assertContains(response, "ESET")
    assertNotContains(response, "Pantheon")


def test_search_by_title(client, user):
    make_application(user, vacancy__title="Junior Python Developer")
    make_application(user, vacancy__title="Data Analyst")
    response = client.get(reverse("tracker:application_list"), {"q": "python"})
    assertContains(response, "Junior Python Developer")
    assertNotContains(response, "Data Analyst")


def test_application_list_num_queries(client, user, django_assert_num_queries):
    for _ in range(5):
        make_application(user)
    # Сессия + пользователь + отклики вместе с вакансиями и компаниями.
    with django_assert_num_queries(3):
        client.get(reverse("tracker:application_list"))


# --- Страница отклика ---


def test_detail_shows_events_newest_first(client, user):
    application = make_application(user)
    EventFactory(
        application=application, text="Old event", happened_at=timezone.now() - timedelta(days=5)
    )
    EventFactory(application=application, text="New event", happened_at=timezone.now())
    content = client.get(application.get_absolute_url()).content.decode()
    assert content.index("New event") < content.index("Old event")


def test_application_detail_num_queries(client, user, django_assert_num_queries):
    application = make_application(user)
    EventFactory.create_batch(3, application=application)
    AttachmentFactory.create_batch(2, application=application)
    # Сессия + пользователь + отклик с вакансией, компанией и прошлой попыткой
    # + события + вложения + более поздние попытки.
    with django_assert_num_queries(6):
        client.get(application.get_absolute_url())


def test_foreign_application_404(client, user):
    foreign = ApplicationFactory()
    assert client.get(foreign.get_absolute_url()).status_code == 404
    url = reverse("tracker:application_add_event", args=[foreign.pk])
    assert client.post(url, {"type": "note"}).status_code == 404


# --- Маленькие формы на странице отклика ---


def test_add_event(client, user):
    application = make_application(user)
    response = client.post(
        reverse("tracker:application_add_event", args=[application.pk]),
        {"type": "call", "happened_at": "2026-10-20T14:30", "text": "HR called"},
    )
    assert response.status_code == 302
    assert response.url == application.get_absolute_url()
    assert application.events.get().text == "HR called"


def test_add_event_invalid_rerenders_page_with_errors(client, user):
    application = make_application(user)
    response = client.post(
        reverse("tracker:application_add_event", args=[application.pk]), {"text": "no type"}
    )
    assert response.status_code == 200
    assert not application.events.exists()


def test_change_status_writes_event(client, user):
    application = make_application(user)
    response = client.post(
        reverse("tracker:application_change_status", args=[application.pk]),
        {"status": "interview", "comment": "Tue 10:00"},
    )
    assert response.status_code == 302
    application.refresh_from_db()
    assert application.status == Application.Status.INTERVIEW
    event = application.events.get()
    assert event.type == ApplicationEvent.EventType.STATUS_CHANGE
    assert "Tue 10:00" in event.text


def test_add_attachment(client, user):
    application = make_application(user)
    response = client.post(
        reverse("tracker:application_add_attachment", args=[application.pk]),
        {"label": "Cover letter", "file": SimpleUploadedFile("letter.pdf", b"%PDF-1.4")},
    )
    assert response.status_code == 302
    assert application.attachments.get().label == "Cover letter"


def test_add_attachment_bad_file_rerenders(client, user):
    application = make_application(user)
    response = client.post(
        reverse("tracker:application_add_attachment", args=[application.pk]),
        {"label": "Nope", "file": SimpleUploadedFile("virus.exe", b"MZ")},
    )
    assert response.status_code == 200
    assert not application.attachments.exists()


def test_actions_are_post_only(client, user):
    application = make_application(user)
    for name in (
        "application_add_event",
        "application_change_status",
        "application_add_attachment",
    ):
        assert client.get(reverse(f"tracker:{name}", args=[application.pk])).status_code == 405


# --- Найдено на финальном ревью ---


def test_change_status_to_same_status_is_form_error(client, user):
    # Случайный клик «Update status» без смены статуса не должен ни писать
    # «Applied → Applied», ни гасить напоминание в needs_attention.
    application = make_application(user, applied_at=(timezone.now() - timedelta(days=10)).date())
    response = client.post(
        reverse("tracker:application_change_status", args=[application.pk]), {"status": "applied"}
    )
    assert response.status_code == 200
    assert not application.events.exists()
    assert application in Application.objects.needs_attention(user)


def test_attachment_download_own(client, user):
    attachment = AttachmentFactory(application__vacancy__company__owner=user)
    response = client.get(reverse("tracker:attachment_download", args=[attachment.pk]))
    assert response.status_code == 200


def test_attachment_download_foreign_404(client, user):
    attachment = AttachmentFactory()
    response = client.get(reverse("tracker:attachment_download", args=[attachment.pk]))
    assert response.status_code == 404


def test_attachment_download_anonymous_redirects_to_login(client):
    attachment = AttachmentFactory()
    response = client.get(reverse("tracker:attachment_download", args=[attachment.pk]))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_media_has_no_public_route_even_in_debug(settings):
    # Files go only through attachment_download (owner check). In DEBUG the
    # project used to add a public /media/ route; make sure it's gone.
    settings.DEBUG = True
    importlib.reload(config.urls)
    clear_url_caches()
    try:
        with pytest.raises(Resolver404):
            resolve("/media/attachments/2026/10/cv.pdf")
    finally:
        settings.DEBUG = False
        importlib.reload(config.urls)
        clear_url_caches()


# --- Архив закрытых откликов ---


def make_closed_set(user):
    for status, title in [
        ("applied", "Open applied"),
        ("offer", "Got an offer"),
        ("rejected", "Was rejected"),
        ("no_response", "Never answered"),
        ("withdrawn", "I withdrew"),
    ]:
        make_application(user, status=status, vacancy__title=title)


def test_closed_applications_hidden_by_default(client, user):
    make_closed_set(user)
    response = client.get(reverse("tracker:application_list"))
    assertContains(response, "Open applied")
    assertContains(response, "Got an offer")
    for hidden in ("Was rejected", "Never answered", "I withdrew"):
        assertNotContains(response, hidden)


def test_archive_toggle_shows_closed(client, user):
    make_closed_set(user)
    response = client.get(reverse("tracker:application_list"), {"archive": "1"})
    for title in ("Open applied", "Was rejected", "Never answered", "I withdrew"):
        assertContains(response, title)


def test_explicit_status_filter_shows_closed_status(client, user):
    make_closed_set(user)
    response = client.get(reverse("tracker:application_list"), {"status": "rejected"})
    assertContains(response, "Was rejected")
    assertNotContains(response, "Open applied")
