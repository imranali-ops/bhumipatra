from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("records.urls")),
    path("api/", include("mutations.urls")),
]
