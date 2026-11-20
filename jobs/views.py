from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import CandidateProfile

from .forms import JobForm
from .matching import candidate_job_sort_key, match_score
from .models import Job


def _employer_or_403(request):
    if request.user.role != "employer":
        return HttpResponseForbidden("Only employers can manage jobs.")


@login_required
def job_list(request):
    denied = _employer_or_403(request)
    if denied:
        return denied
    jobs = Job.objects.filter(employer=request.user, is_deleted=False)
    return render(request, "jobs/job_list.html", {"jobs": jobs})


@login_required
def job_create(request):
    denied = _employer_or_403(request)
    if denied:
        return denied
    if request.method == "POST":
        form = JobForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False)
            job.employer = request.user
            job.save()
            return redirect("jobs:job_list")
    else:
        form = JobForm()
    return render(request, "jobs/job_form.html", {"form": form, "mode": "Create"})


@login_required
def job_edit(request, pk):
    denied = _employer_or_403(request)
    if denied:
        return denied
    job = get_object_or_404(Job, pk=pk, is_deleted=False)
    if job.employer_id != request.user.id:
        return HttpResponseForbidden("Not your job.")
    if request.method == "POST":
        form = JobForm(request.POST, instance=job)
        if form.is_valid():
            form.save()
            return redirect("jobs:job_list")
    else:
        form = JobForm(instance=job)
    return render(request, "jobs/job_form.html", {"form": form, "mode": "Edit"})


@login_required
def job_delete(request, pk):
    denied = _employer_or_403(request)
    if denied:
        return denied
    job = get_object_or_404(Job, pk=pk, is_deleted=False)
    if job.employer_id != request.user.id:
        return HttpResponseForbidden("Not your job.")
    if job.has_dependents():
        return HttpResponse("Cannot delete: job has applications or slots.", status=409)
    if request.method == "POST":
        job.is_deleted = True
        job.save()
        return redirect("jobs:job_list")
    return render(request, "jobs/job_delete.html", {"job": job})


@login_required
def candidate_dashboard(request):
    if request.user.role != "candidate":
        return HttpResponseForbidden("Only candidates see the job dashboard.")
    profile, _ = CandidateProfile.objects.get_or_create(user=request.user)
    jobs = Job.objects.filter(is_deleted=False)
    scored = [(match_score(profile.skills, job.required_skills), job) for job in jobs]
    scored.sort(key=candidate_job_sort_key)
    return render(request, "jobs/candidate_dashboard.html", {"scored": scored})


@login_required
def job_detail(request, pk):
    job = get_object_or_404(Job, pk=pk, is_deleted=False)
    score = None
    if request.user.role == "candidate":
        profile, _ = CandidateProfile.objects.get_or_create(user=request.user)
        score = match_score(profile.skills, job.required_skills)
    return render(request, "jobs/job_detail.html", {"job": job, "score": score})