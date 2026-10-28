from django.contrib import admin
from django.urls import include, path

# No public /media/ route, not even in DEBUG: uploaded CVs and letters are
# private and are served only by tracker:attachment_download (owner check).
urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("api/", include("api.urls")),
    # set_language: the header's language switch posts here.
    path("i18n/", include("django.conf.urls.i18n")),
    path("", include("tracker.urls")),
]
