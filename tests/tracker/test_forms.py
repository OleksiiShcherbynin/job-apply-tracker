from django.core.files.uploadedfile import SimpleUploadedFile

from tracker.forms import AttachmentForm


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
