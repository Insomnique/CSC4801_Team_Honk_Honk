from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import JobForm
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