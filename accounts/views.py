from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import (
    CandidateProfileForm,
    EmployerProfileForm,
    RegisterForm,
)
from .models import CandidateProfile, EmployerProfile


def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("accounts:dashboard")
    else:
        form = RegisterForm()

    return render(request, "accounts/register.html", {"form": form})


@login_required
def dashboard(request):
    if request.user.role == "employer":
        return render(request, "accounts/employer_dashboard.html")
    return render(request, "accounts/candidate_dashboard.html")


@login_required
def candidate_profile(request):
    if request.user.role != "candidate":
        return HttpResponseForbidden("Only candidates can edit a candidate profile.")
    profile, _ = CandidateProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = CandidateProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            return redirect("accounts:dashboard")
    else:
        form = CandidateProfileForm(instance=profile)
    return render(request, "accounts/candidate_profile.html", {"form": form})


@login_required
def employer_profile(request):
    if request.user.role != "employer":
        return HttpResponseForbidden("Only employers can edit an employer profile.")
    profile, _ = EmployerProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = EmployerProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            return redirect("accounts:dashboard")
    else:
        form = EmployerProfileForm(instance=profile)
    return render(request, "accounts/employer_profile.html", {"form": form})