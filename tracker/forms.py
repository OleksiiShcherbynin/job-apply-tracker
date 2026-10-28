from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from .models import Application, ApplicationEvent, Attachment, Company, Vacancy

# Guard against mess and mistakes, not against attackers: every user only
# uploads into their own tracker.
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".odt", ".txt"}
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB


def validate_upload(uploaded):
    extension = Path(uploaded.name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValidationError(
            gettext("File type %(extension)s not allowed. Use: %(allowed)s.")
            % {"extension": extension or gettext("(none)"), "allowed": allowed}
        )
    if uploaded.size > MAX_UPLOAD_SIZE:
        raise ValidationError(gettext("File is larger than 5 MB."))


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
        labels = {"file": _("File"), "label": _("Label")}

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        validate_upload(uploaded)
        return uploaded


class CompanyForm(OwnedModelForm):
    class Meta:
        model = Company
        fields = ["name", "website", "notes"]
        labels = {"name": _("Name"), "website": _("Website"), "notes": _("Notes")}

    def clean_name(self):
        name = self.cleaned_data["name"]
        same_name = Company.objects.filter(owner=self.owner, name__iexact=name)
        others = same_name.exclude(pk=self.instance.pk)
        if others.exists():
            raise forms.ValidationError(gettext("You already have a company with this name."))

        return name


class VacancyForm(OwnedModelForm):
    class Meta:
        model = Vacancy
        fields = ["company", "title", "url", "salary", "location"]
        labels = {
            "company": _("Company"),
            "title": _("Title"),
            "url": _("Link to the posting"),
            "salary": _("Salary"),
            "location": _("Location"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["company"].queryset = Company.objects.filter(owner=self.owner)


class ApplyForm(forms.Form):
    """Form behind the "I applied" button: when, notes, and optionally the file sent."""

    applied_at = forms.DateField(
        label=_("Applied on"),
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text=_("When you actually sent it — may be in the past."),
    )
    notes = forms.CharField(
        label=_("Notes"), widget=forms.Textarea(attrs={"rows": 3}), required=False
    )
    file = forms.FileField(
        label=_("File"), required=False, help_text=_("CV or cover letter you sent (optional).")
    )
    label = forms.CharField(
        label=_("Label"), max_length=100, required=False, help_text=_('e.g. "CV v3 EN"')
    )

    def __init__(self, *args, previous_attempts=(), **kwargs):
        super().__init__(*args, **kwargs)
        # Applying again to a reposted vacancy must be a conscious decision.
        if previous_attempts:
            self.fields["apply_again"] = forms.BooleanField(
                label=_("Yes, apply again"), required=True
            )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if uploaded:
            validate_upload(uploaded)
        return uploaded

    def clean(self):
        cleaned = super().clean()
        uploaded = cleaned.get("file")
        if uploaded and not cleaned.get("label"):
            # Default label from the file name, cut to Attachment.label's limit:
            # real CV file names easily exceed 100 characters.
            max_length = Attachment._meta.get_field("label").max_length
            cleaned["label"] = Path(uploaded.name).stem[:max_length]
        return cleaned


class DismissForm(forms.ModelForm):
    class Meta:
        model = Vacancy
        fields = ["dismiss_reason"]
        labels = {"dismiss_reason": _("Why not?")}


class EventForm(forms.ModelForm):
    class Meta:
        model = ApplicationEvent
        fields = ["type", "happened_at", "text"]
        labels = {"type": _("Type"), "happened_at": _("When"), "text": _("Text")}
        widgets = {
            "happened_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "text": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Status changes go only through Application.change_status, so the
        # timeline and the status field can never disagree.
        self.fields["type"].choices = [
            (value, label)
            for value, label in self.fields["type"].choices
            if value != ApplicationEvent.EventType.STATUS_CHANGE
        ]


class StatusChangeForm(forms.Form):
    status = forms.ChoiceField(label=_("Status"), choices=Application.Status.choices)
    comment = forms.CharField(label=_("Comment"), required=False)

    def __init__(self, *args, current_status=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_status = current_status

    def clean_status(self):
        status = self.cleaned_data["status"]
        # A no-op "change" would write "Applied → Applied" and reset the
        # needs-attention clock; news without a status change is an event.
        if status == self.current_status:
            raise ValidationError(
                gettext(
                    "The application already has this status. "
                    "To record news without changing it, add an event."
                )
            )
        return status


class VacancyDeleteForm(forms.Form):
    """Deleting a vacancy that has an application takes the whole history with it,
    so that case needs an explicit tick."""

    def __init__(self, *args, has_application=False, **kwargs):
        super().__init__(*args, **kwargs)
        if has_application:
            self.fields["delete_application"] = forms.BooleanField(
                required=True,
                label=_("Also delete its application with the whole timeline and files"),
            )
