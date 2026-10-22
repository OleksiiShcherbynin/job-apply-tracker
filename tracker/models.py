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
