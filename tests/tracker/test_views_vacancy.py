from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertContains, assertNotContains

from accounts.factories import UserFactory
from tracker.factories import ApplicationFactory, CompanyFactory, VacancyFactory
from tracker.models import Application, ApplicationEvent, Vacancy

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(client):
    user = UserFactory()
    client.force_login(user)
    return user


@pytest.fixture(autouse=True)
def media_in_tmp(settings, tmp_path):
    # Загруженные в тестах файлы не должны оседать в папке проекта.
    settings.MEDIA_ROOT = tmp_path


# --- Входящие ---


def test_inbox_sorted_by_score_desc(client, user):
    VacancyFactory(company__owner=user, title="Low", score=40)
    VacancyFactory(company__owner=user, title="High", score=90)
    content = client.get(reverse("tracker:inbox")).content.decode()
    assert content.index("High") < content.index("Low")


def test_inbox_shows_only_own_inbox_vacancies(client, user):
    VacancyFactory(company__owner=user, title="Fresh one")
    VacancyFactory(company__owner=user, title="Already applied", state=Vacancy.State.APPLIED)
    VacancyFactory(title="Someone else's")
    response = client.get(reverse("tracker:inbox"))
    assertContains(response, "Fresh one")
    assertNotContains(response, "Already applied")
    assertNotContains(response, "Someone else&#x27;s")


def test_inbox_num_queries(client, user, django_assert_num_queries):
    VacancyFactory.create_batch(5, company__owner=user)
    # Сессия + пользователь + вакансии вместе с компаниями (JOIN).
    with django_assert_num_queries(3):
        client.get(reverse("tracker:inbox"))


# --- CRUD вакансий ---


def test_vacancy_create_sets_owner_and_lands_in_inbox(client, user):
    company = CompanyFactory(owner=user)
    response = client.post(
        reverse("tracker:vacancy_add"), {"company": company.pk, "title": "Junior Python"}
    )
    assert response.status_code == 302
    vacancy = Vacancy.objects.get(title="Junior Python")
    assert vacancy.owner == user
    assert vacancy.state == Vacancy.State.INBOX


def test_vacancy_create_with_foreign_company_is_form_error(client, user):
    foreign = CompanyFactory()
    response = client.post(
        reverse("tracker:vacancy_add"), {"company": foreign.pk, "title": "Sneaky"}
    )
    assert response.status_code == 200
    assert not Vacancy.objects.filter(title="Sneaky").exists()


def test_vacancy_list_filters_by_state(client, user):
    VacancyFactory(company__owner=user, title="In inbox")
    VacancyFactory(company__owner=user, title="Dismissed one", state=Vacancy.State.DISMISSED)
    response = client.get(reverse("tracker:vacancy_list"), {"state": "dismissed"})
    assertContains(response, "Dismissed one")
    assertNotContains(response, "In inbox")


def test_vacancy_list_num_queries(client, user, django_assert_num_queries):
    VacancyFactory.create_batch(5, company__owner=user)
    with django_assert_num_queries(3):
        client.get(reverse("tracker:vacancy_list"))


def test_foreign_vacancy_404(client, user):
    foreign = VacancyFactory()
    assert client.get(reverse("tracker:vacancy_edit", args=[foreign.pk])).status_code == 404
    assert client.get(reverse("tracker:vacancy_apply", args=[foreign.pk])).status_code == 404
    assert client.post(reverse("tracker:vacancy_dismiss", args=[foreign.pk])).status_code == 404


def test_delete_vacancy_with_application_shows_error(client, user):
    application = ApplicationFactory(vacancy__company__owner=user)
    response = client.post(
        reverse("tracker:vacancy_delete", args=[application.vacancy.pk]), follow=True
    )
    assert Vacancy.objects.filter(pk=application.vacancy.pk).exists()
    assertContains(response, "has an application")


# --- «Откликнулся» ---


def test_apply_get_renders_form(client, user):
    vacancy = VacancyFactory(company__owner=user)
    response = client.get(reverse("tracker:vacancy_apply", args=[vacancy.pk]))
    assert response.status_code == 200
    assertContains(response, 'name="applied_at"')


def test_apply_creates_application_and_event_and_marks_vacancy(client, user):
    vacancy = VacancyFactory(company__owner=user)
    response = client.post(
        reverse("tracker:vacancy_apply", args=[vacancy.pk]),
        {"applied_at": timezone.localdate().isoformat(), "notes": "Sent via Profesia"},
    )
    application = Application.objects.get(vacancy=vacancy)
    assert response.status_code == 302
    assert response.url == reverse("tracker:application_detail", args=[application.pk])
    assert application.owner == user
    assert application.notes == "Sent via Profesia"
    assert application.events.filter(type=ApplicationEvent.EventType.STATUS_CHANGE).count() == 1
    vacancy.refresh_from_db()
    assert vacancy.state == Vacancy.State.APPLIED


def test_apply_backdated_counts_for_needs_attention(client, user):
    # Отклик, отправленный 10 дней назад и занесённый только сегодня, уже «залежался».
    vacancy = VacancyFactory(company__owner=user)
    applied = timezone.localdate() - timedelta(days=10)
    client.post(
        reverse("tracker:vacancy_apply", args=[vacancy.pk]), {"applied_at": applied.isoformat()}
    )
    assert Application.objects.needs_attention(user).filter(vacancy=vacancy).exists()


def test_apply_with_file_creates_attachment(client, user):
    vacancy = VacancyFactory(company__owner=user)
    client.post(
        reverse("tracker:vacancy_apply", args=[vacancy.pk]),
        {
            "applied_at": timezone.localdate().isoformat(),
            "file": SimpleUploadedFile("cv.pdf", b"%PDF-1.4"),
            "label": "CV v3 EN",
        },
    )
    attachment = Application.objects.get(vacancy=vacancy).attachments.get()
    assert attachment.label == "CV v3 EN"


def test_apply_with_bad_file_creates_nothing(client, user):
    vacancy = VacancyFactory(company__owner=user)
    response = client.post(
        reverse("tracker:vacancy_apply", args=[vacancy.pk]),
        {
            "applied_at": timezone.localdate().isoformat(),
            "file": SimpleUploadedFile("virus.exe", b"MZ"),
        },
    )
    assert response.status_code == 200
    assert not Application.objects.filter(vacancy=vacancy).exists()


def test_apply_on_already_applied_redirects_to_existing(client, user):
    application = ApplicationFactory(vacancy__company__owner=user)
    response = client.post(
        reverse("tracker:vacancy_apply", args=[application.vacancy.pk]),
        {"applied_at": timezone.localdate().isoformat()},
    )
    assert response.status_code == 302
    assert response.url == reverse("tracker:application_detail", args=[application.pk])
    assert Application.objects.filter(vacancy=application.vacancy).count() == 1


# --- «Отклонить» ---


def test_dismiss_sets_state_and_reason(client, user):
    vacancy = VacancyFactory(company__owner=user)
    response = client.post(
        reverse("tracker:vacancy_dismiss", args=[vacancy.pk]), {"dismiss_reason": "Senior only"}
    )
    assert response.status_code == 302
    vacancy.refresh_from_db()
    assert vacancy.state == Vacancy.State.DISMISSED
    assert vacancy.dismiss_reason == "Senior only"


def test_dismiss_get_not_allowed(client, user):
    vacancy = VacancyFactory(company__owner=user)
    assert client.get(reverse("tracker:vacancy_dismiss", args=[vacancy.pk])).status_code == 405


def test_apply_with_long_filename_and_no_label(client, user):
    # Реальные имена файлов бывают длиннее 100 символов (лимит подписи).
    vacancy = VacancyFactory(company__owner=user)
    long_name = "Oleksii_Shcherbynin_CV_" + "Junior_Python_Developer_" * 5 + "EN.pdf"
    response = client.post(
        reverse("tracker:vacancy_apply", args=[vacancy.pk]),
        {
            "applied_at": timezone.localdate().isoformat(),
            "file": SimpleUploadedFile(long_name, b"%PDF-1.4"),
        },
    )
    assert response.status_code == 302
    label = Application.objects.get(vacancy=vacancy).attachments.get().label
    assert 0 < len(label) <= 100
