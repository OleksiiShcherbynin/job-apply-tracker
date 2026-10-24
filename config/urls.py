from django.contrib import admin
from django.urls import include, path

# No public /media/ route, not even in DEBUG: uploaded CVs and letters are
# private and are served only by tracker:attachment_download (owner check).
urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("tracker.urls")),
]
