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

import json
from django.utils.safestring import mark_safe

from jobs.models import Application, Booking, Job
from jobs.matching import match_score, candidate_job_sort_key


def home(request):
    return render(request, "home.html")


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
    
    profile, _ = CandidateProfile.objects.get_or_create(user=request.user)

    # First 3 applications (same order as My Applications: newest first)
    applications = (
        Application.objects.filter(candidate=request.user)
        .select_related("job", "job__employer", "job__employer__employer_profile")
        [:3]
    )

    # First 3 recommended jobs by match score
    jobs = Job.objects.filter(is_deleted=False)
    scored = [(match_score(profile.skills, job.required_skills), job) for job in jobs]
    scored.sort(key=candidate_job_sort_key)
    recommended = scored[:3]

    # Booked interviews for the calendar
    bookings = (
        Booking.objects.filter(application__candidate=request.user)
        .select_related(
            "slot",
            "application__job",
            "application__job__employer",
            "application__job__employer__employer_profile",
        )
    )
    interviews = []
    for b in bookings:
        start = b.slot.start_time
        end = b.slot.end_time
        emp = b.application.job.employer
        company = (
            getattr(getattr(emp, "employer_profile", None), "company_name", "")
            or emp.username
        )
        interviews.append({
            "date": start.strftime("%Y-%m-%d"),
            "time": f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}",
            "with": company,
            "job": b.application.job.title,
        })

    return render(request, "accounts/candidate_dashboard.html", {
        "applications": applications,
        "recommended": recommended,
        "interviews": interviews,
        "profile_form": CandidateProfileForm(instance=profile),
    })


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