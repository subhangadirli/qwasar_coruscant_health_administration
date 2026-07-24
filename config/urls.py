from django.contrib import admin
from django.urls import include, path

from apps.dashboard.views import health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health"),
    path("accounts/", include("apps.accounts.urls")),
    path("records/", include("apps.records.urls")),
    path("orders/", include("apps.orders.urls")),
    path("", include("apps.dashboard.urls")),
]
