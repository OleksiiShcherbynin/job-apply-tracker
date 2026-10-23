from django.urls import path

from . import views

app_name = "tracker"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("inbox/", views.InboxView.as_view(), name="inbox"),
    # Companies
    path("companies/", views.CompanyListView.as_view(), name="company_list"),
    path("companies/add/", views.CompanyCreateView.as_view(), name="company_add"),
    path("companies/<int:pk>/edit/", views.CompanyUpdateView.as_view(), name="company_edit"),
    path("companies/<int:pk>/delete/", views.CompanyDeleteView.as_view(), name="company_delete"),
    # Vacancies
    path("vacancies/", views.VacancyListView.as_view(), name="vacancy_list"),
    path("vacancies/add/", views.VacancyCreateView.as_view(), name="vacancy_add"),
    path("vacancies/<int:pk>/edit/", views.VacancyUpdateView.as_view(), name="vacancy_edit"),
    path("vacancies/<int:pk>/delete/", views.VacancyDeleteView.as_view(), name="vacancy_delete"),
    path("vacancies/<int:pk>/apply/", views.VacancyApplyView.as_view(), name="vacancy_apply"),
    path("vacancies/<int:pk>/dismiss/", views.VacancyDismissView.as_view(), name="vacancy_dismiss"),
    # Applications
    path(
        "applications/<int:pk>/",
        views.ApplicationDetailView.as_view(),
        name="application_detail",
    ),
]
