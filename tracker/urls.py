from django.urls import path

from . import views

app_name = "tracker"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("companies/", views.CompanyListView.as_view(), name="company_list"),
    path("companies/add/", views.CompanyCreateView.as_view(), name="company_add"),
    path("companies/<int:pk>/edit/", views.CompanyUpdateView.as_view(), name="company_edit"),
    path("companies/<int:pk>/delete/", views.CompanyDeleteView.as_view(), name="company_delete"),
]
