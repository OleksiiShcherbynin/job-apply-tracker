from django.contrib import admin

from .models import Application, ApplicationEvent, Attachment, Company, Vacancy


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "website", "created_at")
    search_fields = ("name",)


@admin.register(Vacancy)
class VacancyAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "state", "score", "source")
    list_filter = ("state", "source")
    search_fields = ("title", "company__name")


class ApplicationEventInline(admin.TabularInline):
    model = ApplicationEvent
    extra = 0


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("vacancy", "status", "applied_at", "owner")
    list_filter = ("status",)
    inlines = [ApplicationEventInline, AttachmentInline]
