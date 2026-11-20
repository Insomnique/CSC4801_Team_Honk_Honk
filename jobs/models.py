from django.conf import settings
from django.db import models


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
        # slots check added when Slot model exists (FP-SCHED-1)
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