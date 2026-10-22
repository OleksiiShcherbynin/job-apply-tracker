from django.conf import settings
from django.db import models


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


class Vacancy(TimeStampedModel):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        JOB_AI_ASSIST = "job_ai_assist", "job-ai-assist"

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
    url = models.URLField(blank=True)
    source = models.CharField(max_length=20, choices=Source, default=Source.MANUAL)
    # Profesia offer id; basis for idempotent pushes from job-ai-assist.
    # null (not "") on purpose: the conditional unique constraint must skip
    # absent ids, and empty strings would collide with each other.
    external_id = models.CharField(max_length=50, null=True, blank=True)  # noqa: DJ001
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    score_reasons = models.TextField(blank=True)
    salary = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=10, choices=State, default=State.INBOX)
    dismiss_reason = models.TextField(blank=True)

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
