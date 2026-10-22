from datetime import timedelta

from django.db import models
from django.db.models import F, Max, Q
from django.utils import timezone


class VacancyQuerySet(models.QuerySet):
    def for_owner(self, user):
        return self.filter(owner=user)

    def inbox(self):
        # self.model — класс Vacancy: берём его State без импорта (иначе
        # был бы циклический импорт models <-> managers).
        return self.filter(state=self.model.State.INBOX).order_by(
            F("score").desc(nulls_last=True), "-created_at"
        )


class ApplicationQuerySet(models.QuerySet):
    def for_owner(self, user):
        return self.filter(owner=user)

    def needs_attention(self, owner):
        """Active applications with no movement for owner.follow_up_days.

        Applications without any events fall back to applied_at: otherwise
        MAX(happened_at) is NULL and they would silently drop out.
        """
        cutoff = timezone.now() - timedelta(days=owner.follow_up_days)
        return (
            self.filter(owner=owner, status__in=self.model.ACTIVE_STATUSES)
            .annotate(last_activity=Max("events__happened_at"))
            .filter(
                Q(last_activity__lt=cutoff)
                | Q(last_activity__isnull=True, applied_at__lt=cutoff.date())
            )
        )
