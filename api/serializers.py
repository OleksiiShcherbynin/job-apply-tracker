from rest_framework import serializers

from tracker.models import Vacancy

MAX_BATCH = 200


class VacancyItemSerializer(serializers.Serializer):
    """One vacancy as job-ai-assist sends it (the contract in the Stage 2 spec)."""

    external_id = serializers.CharField(max_length=50)
    title = serializers.CharField(max_length=255)
    company = serializers.CharField(max_length=200, required=False, allow_blank=True)
    url = serializers.URLField(max_length=500)
    location = serializers.CharField(max_length=200, required=False, allow_blank=True)
    salary = serializers.CharField(max_length=200, required=False, allow_blank=True)
    score = serializers.IntegerField(min_value=0, max_value=100)
    score_stage = serializers.ChoiceField(choices=Vacancy.ScoreStage.choices)
    # Blank lines are tolerated (and dropped on save): rejecting the whole item
    # for an empty reason would lose the vacancy, since invalid items aren't retried.
    reasons_en = serializers.ListField(
        child=serializers.CharField(allow_blank=True), required=False
    )
    reasons_ru = serializers.ListField(
        child=serializers.CharField(allow_blank=True), required=False
    )
    first_seen_at = serializers.DateTimeField(required=False, allow_null=True)


class VacancyBatchSerializer(serializers.Serializer):
    # Items stay raw JSON here: each one is validated on its own so that a bad
    # item is reported per item instead of rejecting the whole batch.
    vacancies = serializers.ListField(
        child=serializers.JSONField(), max_length=MAX_BATCH, allow_empty=True
    )


class IngestResultSerializer(serializers.Serializer):
    external_id = serializers.CharField()
    status = serializers.ChoiceField(choices=["created", "updated", "invalid"])
    id = serializers.IntegerField(required=False)
    errors = serializers.DictField(required=False)


class IngestResponseSerializer(serializers.Serializer):
    results = IngestResultSerializer(many=True)


class ClosedItemSerializer(serializers.Serializer):
    """One closed posting as job-ai-assist reports it (the Stage 3 spec)."""

    external_id = serializers.CharField(max_length=50)
    seen_at = serializers.DateTimeField()


class ClosedBatchSerializer(serializers.Serializer):
    # Raw items, validated one by one, as in VacancyBatchSerializer.
    closed = serializers.ListField(
        child=serializers.JSONField(), max_length=MAX_BATCH, allow_empty=True
    )


class ClosedResultSerializer(serializers.Serializer):
    external_id = serializers.CharField()
    status = serializers.ChoiceField(choices=["closed", "unchanged", "unknown", "invalid"])
    errors = serializers.DictField(required=False)


class ClosedResponseSerializer(serializers.Serializer):
    results = ClosedResultSerializer(many=True)


class OfferToCheckSerializer(serializers.Serializer):
    external_id = serializers.CharField()
    url = serializers.URLField()


class ToCheckResponseSerializer(serializers.Serializer):
    vacancies = OfferToCheckSerializer(many=True)
