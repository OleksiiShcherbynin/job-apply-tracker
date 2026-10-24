import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.factories import UserFactory
from tracker.factories import CompanyFactory
from tracker.forms import AttachmentForm, CompanyForm, EventForm, StatusChangeForm, VacancyForm
from tracker.models import Application, ApplicationEvent


def make_form(filename, size=1024):
    upload = SimpleUploadedFile(filename, b"x" * size)
    return AttachmentForm(data={"label": "CV v3 EN"}, files={"file": upload})


def test_attachment_form_accepts_pdf():
    form = make_form("cv.pdf")
    assert form.is_valid(), form.errors


def test_rejects_exe_extension():
    form = make_form("definitely_cv.exe")
    assert not form.is_valid()
    assert "file" in form.errors


def test_rejects_oversized_file():
    form = make_form("cv.pdf", size=6 * 1024 * 1024)
    assert not form.is_valid()
    assert "file" in form.errors


# --- CompanyForm (пишет Алексей) ---


@pytest.mark.django_db
def test_company_form_valid():
    form = CompanyForm(data={"name": "ESET", "website": "https://eset.com"}, owner=UserFactory())
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_company_form_rejects_duplicate_name_of_same_owner():
    existing = CompanyFactory(name="ESET")
    form = CompanyForm(data={"name": "ESET"}, owner=existing.owner)
    assert not form.is_valid()
    assert "name" in form.errors


@pytest.mark.django_db
def test_company_form_duplicate_check_ignores_case():
    existing = CompanyFactory(name="ESET")
    form = CompanyForm(data={"name": "eset"}, owner=existing.owner)
    assert not form.is_valid()
    assert "name" in form.errors


@pytest.mark.django_db
def test_company_form_same_name_allowed_for_other_owner():
    CompanyFactory(name="ESET")
    form = CompanyForm(data={"name": "ESET"}, owner=UserFactory())
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_company_form_edit_keeps_own_name():
    company = CompanyFactory(name="ESET")
    data = {"name": "ESET", "notes": "new note"}
    form = CompanyForm(data=data, instance=company, owner=company.owner)
    assert form.is_valid(), form.errors


# --- VacancyForm (пишет Алексей) ---


@pytest.mark.django_db
def test_vacancy_form_valid():
    company = CompanyFactory()
    form = VacancyForm(data={"company": company.pk, "title": "Junior Python"}, owner=company.owner)
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_vacancy_form_shows_only_own_companies():
    mine = CompanyFactory(name="ESET")
    CompanyFactory(name="Someone Else Inc")  # чужая компания
    form = VacancyForm(owner=mine.owner)
    assert list(form.fields["company"].queryset) == [mine]


@pytest.mark.django_db
def test_vacancy_form_rejects_foreign_company():
    owner = UserFactory()
    foreign = CompanyFactory()  # принадлежит другому пользователю
    form = VacancyForm(data={"company": foreign.pk, "title": "Junior Python"}, owner=owner)
    assert not form.is_valid()
    assert "company" in form.errors


# --- EventForm и StatusChangeForm ---


def test_event_form_valid():
    form = EventForm(data={"type": "call", "happened_at": "2026-10-20T14:30", "text": "HR call"})
    assert form.is_valid(), form.errors


def test_event_form_type_choices_exclude_status_change():
    form = EventForm()
    values = [value for value, label in form.fields["type"].choices]
    assert ApplicationEvent.EventType.STATUS_CHANGE not in values
    assert ApplicationEvent.EventType.CALL in values


def test_event_form_rejects_status_change_type():
    # Смена статуса пишется только через change_status, вручную — нельзя.
    form = EventForm(data={"type": "status_change", "happened_at": "2026-10-20T14:30"})
    assert not form.is_valid()
    assert "type" in form.errors


def test_status_change_form_valid():
    form = StatusChangeForm(data={"status": Application.Status.INTERVIEW, "comment": "Tue 10:00"})
    assert form.is_valid(), form.errors


def test_status_change_form_comment_optional():
    form = StatusChangeForm(data={"status": Application.Status.REJECTED})
    assert form.is_valid(), form.errors


def test_status_change_form_rejects_unknown_status():
    form = StatusChangeForm(data={"status": "hired_by_aliens"})
    assert not form.is_valid()
    assert "status" in form.errors
