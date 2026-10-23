import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.factories import UserFactory
from tracker.factories import CompanyFactory
from tracker.forms import AttachmentForm, CompanyForm


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
