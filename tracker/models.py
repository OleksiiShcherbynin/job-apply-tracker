from datetime import date, datetime

from django.conf import settings
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from .fingerprints import fingerprint
from .managers import ApplicationQuerySet, VacancyQuerySet


class TimeStampedModel(models.Model):
    """Abstract base: adds created_at / updated_at to every domain model."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Company(TimeStampedModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="companies",
    )
    name = models.CharField(max_length=200)
    website = models.URLField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"],
                name="unique_company_per_owner",
            )
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        renamed = self.pk is not None and getattr(self, "_loaded_name", self.name) != self.name
        super().save(*args, **kwargs)
        self._loaded_name = self.name
        if renamed:
            # Vacancy fingerprints embed the company name; keep them in step.
            for vacancy in self.vacancies.all():
                vacancy.company = self
                vacancy.save(update_fields=["fingerprint"])

    @classmethod
    def from_db(cls, db, field_names, values):
        # Remember the name as loaded, so save() can tell a rename.
        instance = super().from_db(db, field_names, values)
        instance._loaded_name = instance.__dict__.get("name")
        return instance


class Vacancy(TimeStampedModel):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        JOB_AI_ASSIST = "job_ai_assist", "job-ai-assist"

    class ScoreStage(models.TextChoices):
        ROUGH = "rough", "Rough"
        FINAL = "final", "Final"

    class State(models.TextChoices):
        INBOX = "inbox", "Inbox"
        APPLIED = "applied", "Applied"
        DISMISSED = "dismissed", "Dismissed"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vacancies",
    )
    # PROTECT: deleting a company must not silently take vacancies with it.
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="vacancies",
    )
    title = models.CharField(max_length=255)
    url = models.URLField(max_length=500, blank=True)
    source = models.CharField(max_length=20, choices=Source, default=Source.MANUAL)
    # Profesia offer id; basis for idempotent pushes from job-ai-assist.
    # null (not "") on purpose: the conditional unique constraint must skip
    # absent ids, and empty strings would collide with each other.
    external_id = models.CharField(max_length=50, null=True, blank=True)  # noqa: DJ001
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    score_stage = models.CharField(max_length=5, choices=ScoreStage, blank=True)
    score_reasons = models.TextField(blank=True)  # English
    score_reasons_ru = models.TextField(blank=True)
    salary = models.CharField(max_length=200, blank=True)
    location = models.CharField(max_length=200, blank=True)
    # When job-ai-assist first saw the offer; the vacancy's age counts from here
    # (falls back to created_at for hand-entered ones).
    first_seen_at = models.DateTimeField(null=True, blank=True)
    # company|title, normalized; how reposts under a new offer id are recognized.
    fingerprint = models.CharField(max_length=500, db_index=True, editable=False, default="")
    state = models.CharField(max_length=10, choices=State, default=State.INBOX)
    dismiss_reason = models.TextField(blank=True)
    # When the tracker learned the posting closed (reported by job-ai-assist).
    closed_at = models.DateTimeField(null=True, blank=True)

    objects = VacancyQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "external_id"],
                condition=models.Q(external_id__isnull=False),
                name="unique_external_id_per_owner",
            )
        ]

    def __str__(self):
        return f"{self.title} @ {self.company}"

    def save(self, *args, **kwargs):
        self.fingerprint = fingerprint(self.company.name, self.title)
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {*kwargs["update_fields"], "fingerprint"}
        super().save(*args, **kwargs)

    def previous_applications(self):
        """The owner's applications to the same posting under other offer ids."""
        return (
            Application.objects.filter(owner=self.owner, vacancy__fingerprint=self.fingerprint)
            .exclude(vacancy=self)
            .select_related("vacancy")
            .order_by("-applied_at", "-pk")
        )

    def mark_applied(self, applied_at, notes="", previous_attempt=None):
        """Record that the user applied: Application + first timeline event.

        The event is dated on applied_at, not "now": an application entered
        a few days late must still age correctly in needs_attention.
        """
        with transaction.atomic():
            application = Application.objects.create(
                owner=self.owner,
                vacancy=self,
                applied_at=applied_at,
                notes=notes,
                previous_attempt=previous_attempt,
            )
            ApplicationEvent.objects.create(
                application=application,
                type=ApplicationEvent.EventType.STATUS_CHANGE,
                happened_at=timezone.make_aware(
                    datetime.combine(applied_at, timezone.localtime().time())
                ),
                text=f"→ {Application.Status.APPLIED.label}",
            )
            self.state = self.State.APPLIED
            self.save(update_fields=["state", "updated_at"])
        return application


class Application(TimeStampedModel):
    class Status(models.TextChoices):
        APPLIED = "applied", "Applied"
        REPLIED = "replied", "Replied"
        INTERVIEW = "interview", "Interview"
        OFFER = "offer", "Offer"
        REJECTED = "rejected", "Rejected"
        NO_RESPONSE = "no_response", "No response"
        WITHDRAWN = "withdrawn", "Withdrawn"

    # Statuses where the ball may be in the company's court: these feed
    # the needs-attention dashboard.
    ACTIVE_STATUSES = (Status.APPLIED, Status.REPLIED)
    # Finished without an offer; the applications list hides these unless asked.
    CLOSED_STATUSES = (Status.REJECTED, Status.NO_RESPONSE, Status.WITHDRAWN)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    vacancy = models.OneToOneField(
        Vacancy,
        on_delete=models.PROTECT,
        related_name="application",
    )
    status = models.CharField(max_length=12, choices=Status, default=Status.APPLIED)
    applied_at = models.DateField(default=date.today)
    notes = models.TextField(blank=True)
    # The earlier application to the same posting (a company repost), if any.
    previous_attempt = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="later_attempts",
    )

    objects = ApplicationQuerySet.as_manager()

    def __str__(self):
        return f"{self.vacancy} [{self.get_status_display()}]"

    def get_absolute_url(self):
        return reverse("tracker:application_detail", args=[self.pk])

    def change_status(self, new_status, comment="", when=None):
        old_status_display = self.get_status_display()
        # Status and its timeline event change together or not at all.
        with transaction.atomic():
            self.status = new_status
            self.save()
            event = ApplicationEvent.objects.create(
                application=self,
                type=ApplicationEvent.EventType.STATUS_CHANGE,
                happened_at=when or timezone.now(),
                text=f"{old_status_display} → {self.get_status_display()}. {comment}".strip(),
            )
        return event


class ApplicationEvent(TimeStampedModel):
    class EventType(models.TextChoices):
        STATUS_CHANGE = "status_change", "Status change"
        NOTE = "note", "Note"
        CALL = "call", "Call"
        INTERVIEW = "interview", "Interview"
        EMAIL = "email", "Email"

    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="events",
    )
    type = models.CharField(max_length=15, choices=EventType)
    happened_at = models.DateTimeField(default=timezone.now)
    text = models.TextField(blank=True)

    class Meta:
        ordering = ["-happened_at"]

    def __str__(self):
        return f"{self.get_type_display()} @ {self.happened_at:%Y-%m-%d %H:%M}"


class Attachment(TimeStampedModel):
    """A file sent with an application (CV version, cover letter, ...).

    created_at doubles as the upload timestamp.
    """

    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to="attachments/%Y/%m/")
    label = models.CharField(max_length=100)

    def __str__(self):
        return self.label
