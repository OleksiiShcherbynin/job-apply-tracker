from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError

from .models import Attachment, Company


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
    # Guard against mess and mistakes, not against attackers: this is the
    # user's own single-tenant tracker.
    ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".odt", ".txt"}
    MAX_SIZE = 5 * 1024 * 1024  # 5 MB

    class Meta:
        model = Attachment
        fields = ["file", "label"]

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        extension = Path(uploaded.name).suffix.lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(self.ALLOWED_EXTENSIONS))
            raise ValidationError(f"File type {extension or '(none)'} not allowed. Use: {allowed}.")
        if uploaded.size > self.MAX_SIZE:
            raise ValidationError("File is larger than 5 MB.")
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
