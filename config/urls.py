from django.contrib import admin
from django.urls import include, path, reverse_lazy
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(url=reverse_lazy("accounts:home"), permanent=False)),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("jobs/", include("jobs.urls")),
]