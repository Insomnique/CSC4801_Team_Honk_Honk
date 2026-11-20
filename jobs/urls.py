from django.urls import path

from . import views

app_name = "jobs"

urlpatterns = [
    path("", views.job_list, name="job_list"),
    path("new/", views.job_create, name="job_create"),
    path("dashboard/", views.candidate_dashboard, name="candidate_dashboard"),
    path("my-applications/", views.my_applications, name="my_applications"),
    path("applications/<int:pk>/status/", views.update_application_status, name="update_application_status"),
    path("<int:pk>/", views.job_detail, name="job_detail"),
    path("<int:pk>/apply/", views.apply_to_job, name="apply_to_job"),
    path("<int:pk>/applicants/", views.job_applicants, name="job_applicants"),
    path("<int:pk>/edit/", views.job_edit, name="job_edit"),
    path("<int:pk>/delete/", views.job_delete, name="job_delete"),
]