from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from tracker.closing import report_closed
from tracker.ingest import ingest_vacancy
from tracker.models import Vacancy

from .serializers import (
    ClosedBatchSerializer,
    ClosedItemSerializer,
    ClosedResponseSerializer,
    IngestResponseSerializer,
    ToCheckResponseSerializer,
    VacancyBatchSerializer,
    VacancyItemSerializer,
)


class VacancyIngestView(APIView):
    """Batch ingest of scored vacancies for the token's owner."""

    throttle_classes = [UserRateThrottle]

    @extend_schema(request=VacancyBatchSerializer, responses=IngestResponseSerializer)
    def post(self, request):
        batch = VacancyBatchSerializer(data=request.data)
        batch.is_valid(raise_exception=True)
        items = batch.validated_data["vacancies"]
        results = [self._ingest_one(request.user, item) for item in items]
        return Response({"results": results})

    @staticmethod
    def _ingest_one(owner, item) -> dict:
        if not isinstance(item, dict):
            return {
                "external_id": "",
                "status": "invalid",
                "errors": {"non_field_errors": ["Expected a JSON object."]},
            }
        serializer = VacancyItemSerializer(data=item)
        if not serializer.is_valid():
            return {
                "external_id": str(item.get("external_id", "")),
                "status": "invalid",
                "errors": serializer.errors,
            }
        vacancy, status = ingest_vacancy(owner, serializer.validated_data)
        return {"external_id": vacancy.external_id, "status": status, "id": vacancy.pk}


class VacancyToCheckView(APIView):
    """The token owner's offers job-ai-assist should check for a closed posting."""

    throttle_classes = [UserRateThrottle]

    @extend_schema(responses=ToCheckResponseSerializer)
    def get(self, request):
        offers = Vacancy.objects.to_check(request.user).values("external_id", "url")
        return Response({"vacancies": list(offers)})


class VacancyClosedView(APIView):
    """Reports of closed Profesia postings for the token's owner."""

    throttle_classes = [UserRateThrottle]

    @extend_schema(request=ClosedBatchSerializer, responses=ClosedResponseSerializer)
    def post(self, request):
        batch = ClosedBatchSerializer(data=request.data)
        batch.is_valid(raise_exception=True)
        results = [self._close_one(request.user, item) for item in batch.validated_data["closed"]]
        return Response({"results": results})

    @staticmethod
    def _close_one(owner, item) -> dict:
        if not isinstance(item, dict):
            return {
                "external_id": "",
                "status": "invalid",
                "errors": {"non_field_errors": ["Expected a JSON object."]},
            }
        serializer = ClosedItemSerializer(data=item)
        if not serializer.is_valid():
            return {
                "external_id": str(item.get("external_id", "")),
                "status": "invalid",
                "errors": serializer.errors,
            }
        data = serializer.validated_data
        status = report_closed(owner, data["external_id"], data["seen_at"])
        return {"external_id": data["external_id"], "status": status}
