from datetime import timedelta

from django.db import models
from django.db.models import Exists, F, Max, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
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

    def with_age(self):
        # A vacancy is as old as job-ai-assist's first sighting; hand-entered
        # ones count from when they were typed in.
        return self.annotate(age_at=Coalesce("first_seen_at", "created_at"))

    def to_check(self, owner):
        """The owner's offers worth checking for a closed posting.

        An application still waiting for an answer, or an inbox vacancy the
        author would see (scored at least inbox_min_score, or unscored).
        """
        Status = self.model._meta.get_field("application").related_model.Status
        waiting = Q(application__status=Status.APPLIED)
        undecided = (
            Q(application__isnull=True, state=self.model.State.INBOX)
            & (Q(score__gte=owner.inbox_min_score) | Q(score__isnull=True))
        )
        return self.filter(
            waiting | undecided,
            owner=owner,
            external_id__isnull=False,
            closed_at__isnull=True,
        ).order_by("external_id")

    def for_inbox_view(self, owner, *, default=True, unprocessed=False, below_threshold=False):
        """The owner's not-applied vacancies for the chosen inbox views.

        Every such vacancy belongs to exactly one view:
        - default: in the inbox, scored >= the owner's threshold or unscored,
          younger than inbox_fresh_days, and no newer undecided repost exists;
        - unprocessed: the same score rule, but old, hidden by a newer repost,
          or dismissed;
        - below_threshold: scored under the threshold, in the inbox or dismissed.
        """
        State = self.model.State
        cutoff = timezone.now() - timedelta(days=owner.inbox_fresh_days)
        min_score = owner.inbox_min_score

        newer_repost = (
            self.model.objects.with_age()
            .filter(owner=owner, state=State.INBOX, fingerprint=OuterRef("fingerprint"))
            .exclude(pk=OuterRef("pk"))
            .filter(
                Q(age_at__gt=OuterRef("age_at"))
                | Q(age_at=OuterRef("age_at"), pk__gt=OuterRef("pk"))
            )
        )

        scored_enough = Q(score__gte=min_score) | Q(score__isnull=True)
        fresh = Q(age_at__gte=cutoff)
        in_inbox = Q(state=State.INBOX)
        wanted = Q(pk__in=[])
        if default:
            wanted |= in_inbox & scored_enough & fresh & Q(has_newer_repost=False)
        if unprocessed:
            wanted |= scored_enough & (
                (in_inbox & (~fresh | Q(has_newer_repost=True))) | Q(state=State.DISMISSED)
            )
        if below_threshold:
            wanted |= Q(score__lt=min_score, state__in=[State.INBOX, State.DISMISSED])

        # Facts about the same posting under other offer ids, for the card
        # markers. Subqueries keep the page at one query however many cards.
        Application = self.model._meta.get_field("application").related_model
        earlier_application = (
            Application.objects.filter(owner=owner, vacancy__fingerprint=OuterRef("fingerprint"))
            .exclude(vacancy=OuterRef("pk"))
            .order_by("-applied_at", "-pk")
        )
        earlier_dismissal = (
            self.model.objects.filter(
                owner=owner, state=State.DISMISSED, fingerprint=OuterRef("fingerprint")
            )
            .exclude(pk=OuterRef("pk"))
            .order_by("-updated_at")
        )

        return (
            self.filter(owner=owner)
            .with_age()
            .annotate(
                has_newer_repost=Exists(newer_repost),
                prev_application_pk=Subquery(earlier_application.values("pk")[:1]),
                prev_applied_at=Subquery(earlier_application.values("applied_at")[:1]),
                prev_status=Subquery(earlier_application.values("status")[:1]),
                dismissed_before=Exists(earlier_dismissal),
                prev_dismiss_reason=Subquery(earlier_dismissal.values("dismiss_reason")[:1]),
            )
            .filter(wanted)
            .select_related("company")
            .order_by(F("score").desc(nulls_last=True), "-age_at")
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
