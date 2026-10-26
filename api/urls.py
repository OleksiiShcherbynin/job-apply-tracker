from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

from . import views

app_name = "api"

urlpatterns = [
    path("v1/vacancies/", views.VacancyIngestView.as_view(), name="vacancy-ingest"),
    path("v1/vacancies/to-check/", views.VacancyToCheckView.as_view(), name="vacancy-to-check"),
    path("v1/vacancies/closed/", views.VacancyClosedView.as_view(), name="vacancy-closed"),
    # The schema describes the contract and holds no data, so it is public.
    path(
        "schema/",
        SpectacularAPIView.as_view(permission_classes=[AllowAny], authentication_classes=[]),
        name="schema",
    ),
    path(
        "schema/swagger-ui/",
        SpectacularSwaggerView.as_view(
            url_name="api:schema", permission_classes=[AllowAny], authentication_classes=[]
        ),
        name="swagger-ui",
    ),
]
