from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    # Keep the stock auth fieldsets, add our tracker settings section.
    fieldsets = (
        *DjangoUserAdmin.fieldsets,
        ("Tracker", {"fields": ("follow_up_days",)}),
    )
