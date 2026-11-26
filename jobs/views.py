from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import CandidateProfile

from .forms import JobForm
from .matching import candidate_job_sort_key, match_score
from .models import Application, Job

from .forms import JobForm, SlotForm
from .models import Application, Job, Slot

from .models import Application, Booking, Job, Slot
from django.utils import timezone

from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse

def _employer_or_403(request):
    if request.user.role != "employer":
        return HttpResponseForbidden("Only employers can manage jobs.")


@login_required
def job_list(request):
    denied = _employer_or_403(request)
    if denied:
        return denied
    jobs = Job.objects.filter(employer=request.user, is_deleted=False)
    return render(request, "jobs/job_list.html", {"jobs": jobs, "job_form": JobForm()})


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

@login_required
def apply_to_job(request, pk):
    if request.user.role != "candidate":
        return HttpResponseForbidden("Only candidates can apply.")
    job = get_object_or_404(Job, pk=pk, is_deleted=False)
    if request.method != "POST":
        return HttpResponseForbidden("Apply via POST.")
    try:
        with transaction.atomic():
            Application.objects.create(
                candidate=request.user, job=job, status=Application.Status.PENDING
            )
    except IntegrityError:
        return HttpResponse("You have already applied to this job.", status=409)
    return redirect("jobs:my_applications")


@login_required
def my_applications(request):
    if request.user.role != "candidate":
        return HttpResponseForbidden("Only candidates have applications.")
    apps = (
        Application.objects.filter(candidate=request.user)
        .select_related("job", "job__employer", "job__employer__employer_profile")
    )
    return render(request, "jobs/my_applications.html", {"apps": apps})

@login_required
def job_applicants(request, pk):
    if request.user.role != "employer":
        return HttpResponseForbidden("Only employers can view applicants.")
    job = get_object_or_404(Job, pk=pk, is_deleted=False)
    if job.employer_id != request.user.id:
        return HttpResponseForbidden("Not your job.")

    apps = (
        Application.objects.filter(job=job)
        .select_related("candidate", "candidate__candidate_profile", "booking__slot")
    )
    scored = [
        (
            match_score(
                getattr(app.candidate.candidate_profile, "skills", [])
                if hasattr(app.candidate, "candidate_profile") else [],
                job.required_skills,
            ),
            app,
        )
        for app in apps
    ]
    # Sort by score desc, then display name (ci), then candidate id
    scored.sort(
        key=lambda pair: (
            -pair[0],
            (
                getattr(pair[1].candidate, "candidate_profile", None)
                and pair[1].candidate.candidate_profile.display_name
                or pair[1].candidate.username
            ).lower(),
            pair[1].candidate.id,
        )
    )

    template = (
        "jobs/_applicants_table.html"
        if request.headers.get("x-requested-with") == "XMLHttpRequest"
        else "jobs/job_applicants.html"
    )
    return render(request, template, {"job": job, "scored": scored})


@login_required
def update_application_status(request, pk):
    if request.user.role != "employer":
        return HttpResponseForbidden("Only employers can change status.")
    if request.method != "POST":
        return HttpResponseForbidden("POST only.")

    app = get_object_or_404(Application, pk=pk)
    if app.job.employer_id != request.user.id:
        return HttpResponseForbidden("Not your job's application.")

    new_status = request.POST.get("status", "")
    valid = {c[0] for c in Application.Status.choices}
    if new_status not in valid:
        return HttpResponse("Invalid status.", status=400)

    app.status = new_status
    app.save()
    return redirect("jobs:job_applicants", pk=app.job.pk)


@login_required
def slot_list(request):
    if request.user.role != "employer":
        return HttpResponseForbidden("Only employers manage slots.")
    slots = Slot.objects.filter(employer=request.user)
    return render(request, "jobs/slot_list.html", {"slots": slots, "slot_form": SlotForm()})


@login_required
def slot_create(request):
    if request.user.role != "employer":
        return HttpResponseForbidden("Only employers manage slots.")
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
    if request.method == "POST":
        form = SlotForm(request.POST, employer=request.user)
        if form.is_valid():
            slot = form.save(commit=False)
            slot.employer = request.user
            slot.save()
            if is_ajax:
                return JsonResponse({"ok": True})
            return redirect("jobs:slot_list")
        if is_ajax:
            errors = [str(e) for errs in form.errors.values() for e in errs]
            return JsonResponse({"ok": False, "errors": errors}, status=400)
    else:
        form = SlotForm()
    return render(request, "jobs/slot_form.html", {"form": form})


@login_required
def slot_delete(request, pk):
    if request.user.role != "employer":
        return HttpResponseForbidden("Only employers manage slots.")
    slot = get_object_or_404(Slot, pk=pk)
    if slot.employer_id != request.user.id:
        return HttpResponseForbidden("Not your slot.")
    if slot.is_booked():
        return HttpResponse("Cannot delete a booked slot.", status=409)
    if request.method == "POST":
        slot.delete()
        return redirect("jobs:slot_list")
    return render(request, "jobs/slot_delete.html", {"slot": slot})


@login_required
def bookable_slots(request, application_pk):
    if request.user.role != "candidate":
        return HttpResponseForbidden("Only candidates book slots.")
    app = get_object_or_404(Application, pk=application_pk)
    if app.candidate_id != request.user.id:
        return HttpResponseForbidden("Not your application.")

    slots = Slot.objects.filter(
        employer=app.job.employer,
        start_time__gt=timezone.now(),
    ).exclude(booking__isnull=False)

    return render(
        request,
        "jobs/bookable_slots.html",
        {"app": app, "slots": slots, "already_booked": Booking.objects.filter(application=app).exists()},
    )


@login_required
def book_slot(request, slot_pk):
    if request.user.role != "candidate":
        return HttpResponseForbidden("Only candidates book slots.")
    if request.method != "POST":
        return HttpResponseForbidden("POST only.")

    slot = get_object_or_404(Slot, pk=slot_pk)
    application_pk = request.POST.get("application_pk", "")
    if not application_pk.isdigit():
        raise Http404("Application not found.")
    app = get_object_or_404(Application, pk=application_pk)

    # Rule 1: candidate owns the application
    if app.candidate_id != request.user.id:
        return HttpResponseForbidden("Not your application.")
    # Rule 2: slot belongs to the employer of the application's job
    if slot.employer_id != app.job.employer_id:
        return HttpResponseForbidden("Slot is not from this job's employer.")
    # Rule 3: application status is interviewing
    if app.status != Application.Status.INTERVIEWING:
        return HttpResponse("Application is not in Interviewing status.", status=409)
    # Rule 4: slot is in the future
    if slot.start_time <= timezone.now():
        return HttpResponse("Slot is not in the future.", status=409)
    # Rule 5: application has no existing booking
    if Booking.objects.filter(application=app).exists():
        return HttpResponse("Application already has a booking.", status=409)

    try:
        with transaction.atomic():
            Booking.objects.create(application=app, slot=slot)
    except IntegrityError:
        return HttpResponse("Slot already booked", status=409)
    return redirect("jobs:my_applications")