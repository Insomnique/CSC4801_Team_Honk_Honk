from django.conf import settings
from django.db import models
from django.utils import timezone
from datetime import timedelta


class Job(models.Model):
    employer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    required_skills = models.JSONField(default=list, blank=True)  # list of strings
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.title

    def has_dependents(self):
        if self.applications.exists():
            return True
        return False
    
class Application(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        INTERVIEWING = "interviewing", "Interviewing"
        REJECTED = "rejected", "Rejected"
        ACCEPTED = "accepted", "Accepted"

    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    job = models.ForeignKey(
        Job, on_delete=models.CASCADE, related_name="applications"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "job"], name="uniq_candidate_job_application"
            )
        ]
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.candidate.username} -> {self.job.title} ({self.status})"
    


class Slot(models.Model):
    employer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="slots",
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    class Meta:
        ordering = ["start_time", "id"]
        constraints = [
            # FP-SCHED-1: every slot is exactly 30 minutes and ends after it starts.
            # Enforced by the database, so no code path can store an invalid slot.
            models.CheckConstraint(
                condition=models.Q(end_time=models.F("start_time") + timedelta(minutes=30)),
                name="slot_exactly_30_minutes",
            ),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="slot_end_after_start",
            ),
        ]

    def __str__(self):
        return f"{self.employer.username} @ {self.start_time}"

    @property
    def duration_minutes(self):
        return int((self.end_time - self.start_time).total_seconds() // 60)

    def is_future(self):
        return self.start_time > timezone.now()

    def is_valid_duration(self):
        return self.duration_minutes == 30

    def is_booked(self):
        return Booking.objects.filter(slot=self).exists()
    

class Booking(models.Model):
    application = models.OneToOneField(
        Application, on_delete=models.CASCADE, related_name="booking"
    )
    slot = models.OneToOneField(
        Slot, on_delete=models.CASCADE, related_name="booking"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Booking app={self.application_id} slot={self.slot_id}"