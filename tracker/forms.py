from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Attachment, Company, Vacancy

# Guard against mess and mistakes, not against attackers: every user only
# uploads into their own tracker.
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".odt", ".txt"}
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB


def validate_upload(uploaded):
    extension = Path(uploaded.name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValidationError(f"File type {extension or '(none)'} not allowed. Use: {allowed}.")
    if uploaded.size > MAX_UPLOAD_SIZE:
        raise ValidationError("File is larger than 5 MB.")


class OwnedModelForm(forms.ModelForm):
    """ModelForm for owner-scoped models.

    The view passes owner=request.user. `owner` is never a form field (the user
    must not pick it), so Django skips the (owner, ...) unique constraints during
    validation; owner-aware checks go into clean_<field> using self.owner.
    """

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        self.instance.owner = owner


class AttachmentForm(forms.ModelForm):
    class Meta:
        model = Attachment
        fields = ["file", "label"]

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        validate_upload(uploaded)
        return uploaded


class CompanyForm(OwnedModelForm):
    class Meta:
        model = Company
        fields = ["name", "website", "notes"]

    def clean_name(self):
        name = self.cleaned_data["name"]
        same_name = Company.objects.filter(owner=self.owner, name__iexact=name)
        others = same_name.exclude(pk=self.instance.pk)
        if others.exists():
            raise forms.ValidationError("You already have a company with this name.")

        return name


class VacancyForm(OwnedModelForm):
    class Meta:
        model = Vacancy
        fields = ["company", "title", "url", "salary", "location"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["company"].queryset = Company.objects.filter(owner=self.owner)


class ApplyForm(forms.Form):
    """Form behind the "I applied" button: when, notes, and optionally the file sent."""

    applied_at = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="When you actually sent it — may be in the past.",
    )
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)
    file = forms.FileField(required=False, help_text="CV or cover letter you sent (optional).")
    label = forms.CharField(max_length=100, required=False, help_text='e.g. "CV v3 EN"')

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if uploaded:
            validate_upload(uploaded)
        return uploaded


class DismissForm(forms.ModelForm):
    class Meta:
        model = Vacancy
        fields = ["dismiss_reason"]
