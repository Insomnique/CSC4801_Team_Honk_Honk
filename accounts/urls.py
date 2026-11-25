from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("home/", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.candidate_profile, name="candidate_profile"),
    path("company/", views.employer_profile, name="employer_profile"),
]