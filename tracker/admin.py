from django.contrib import admin

from .models import Company, Vacancy


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "website", "created_at")
    search_fields = ("name",)


@admin.register(Vacancy)
class VacancyAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "state", "score", "source")
    list_filter = ("state", "source")
    search_fields = ("title", "company__name")
