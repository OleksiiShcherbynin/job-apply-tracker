from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError

from .models import Attachment


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
