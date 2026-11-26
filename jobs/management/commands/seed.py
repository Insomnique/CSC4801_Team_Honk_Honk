"""
Deterministic seed data for local development and demonstration.

Run:  docker compose exec web python manage.py seed
This command WIPES all application data, then repopulates it.
"""
from datetime import datetime, timedelta, timezone as dt_timezone

from django.core.management.base import BaseCommand
from django.core.management.color import no_style
from django.db import connection
from django.utils import timezone

from accounts.models import CandidateProfile, EmployerProfile, User
from jobs.models import Application, Booking, Job, Slot


class Command(BaseCommand):
    help = "Reset and seed deterministic demo data (3 candidates, 2 employers, 3 jobs, 4 statuses, 2 racers)."

    def handle(self, *args, **options):
        self.stdout.write("Wiping existing data...")
        Booking.objects.all().delete()
        Application.objects.all().delete()
        Slot.objects.all().delete()
        Job.objects.all().delete()
        CandidateProfile.objects.all().delete()
        EmployerProfile.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        # Restart ID sequences so every run produces the same IDs (deterministic seed).
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(
                no_style(), [User, CandidateProfile, EmployerProfile, Job, Application, Slot, Booking]
            ):
                cursor.execute(sql)

        self.stdout.write("Creating users...")
        # Employers
        emp1 = User.objects.create_user(
            username="employer_techco", email="techco@example.com",
            password="demo12345", role="employer",
        )
        EmployerProfile.objects.create(
            user=emp1, company_name="TechCo",
            description="We build developer tools.",
        )
        emp2 = User.objects.create_user(
            username="employer_datacorp", email="datacorp@example.com",
            password="demo12345", role="employer",
        )
        EmployerProfile.objects.create(
            user=emp2, company_name="DataCorp",
            description="Data pipelines and analytics.",
        )

        # Candidates
        cand1 = User.objects.create_user(
            username="candidate_alice", email="alice@example.com",
            password="demo12345", role="candidate",
        )
        CandidateProfile.objects.create(
            user=cand1, display_name="Alice",
            skills=["Python", "SQL"],
            resume_text="Alice: 5 years backend development.",
        )
        cand2 = User.objects.create_user(
            username="candidate_bob", email="bob@example.com",
            password="demo12345", role="candidate",
        )
        CandidateProfile.objects.create(
            user=cand2, display_name="Bob",
            skills=["Python"],
            resume_text="Bob: junior Python developer.",
        )

        self.stdout.write("Creating jobs...")
        # Job A: Python+SQL required → Alice 100%, Bob 50%
        job_a = Job.objects.create(
            employer=emp1, title="Backend Engineer",
            description="Build backend services in Python and SQL.",
            required_skills=["Python", "SQL"],
        )
        # Job B: Rust required → both 0%
        job_b = Job.objects.create(
            employer=emp2, title="Rust Systems Engineer",
            description="Systems programming in Rust.",
            required_skills=["Rust"],
        )
        # Job C: no required skills → every candidate scores 100%
        Job.objects.create(
            employer=emp2, title="Graduate Generalist",
            description="Open to all backgrounds; no specific skills required.",
            required_skills=[],
        )

        self.stdout.write("Creating applications covering all four statuses...")
        # Alice → Job A: Interviewing (she can race for a slot)
        app_alice_a = Application.objects.create(
            candidate=cand1, job=job_a, status=Application.Status.INTERVIEWING,
        )
        # Bob → Job A: Interviewing (the other racer)
        app_bob_a = Application.objects.create(
            candidate=cand2, job=job_a, status=Application.Status.INTERVIEWING,
        )
        # Alice → Job B: Pending (she hasn't been reviewed)
        Application.objects.create(
            candidate=cand1, job=job_b, status=Application.Status.PENDING,
        )
        # Bob → Job B: Rejected
        Application.objects.create(
            candidate=cand2, job=job_b, status=Application.Status.REJECTED,
        )

        self.stdout.write("Creating availability slots...")
        # Fixed UTC times so every run is identical. The future slots stay bookable
        # until mid-2027; the past slot is always in the past.
        thirty = timedelta(minutes=30)
        race_start = datetime(2027, 6, 1, 2, 0, tzinfo=dt_timezone.utc)   # 10:00 Perth
        second_start = datetime(2027, 6, 2, 2, 0, tzinfo=dt_timezone.utc)
        past_start = datetime(2025, 1, 1, 2, 0, tzinfo=dt_timezone.utc)
        if race_start <= timezone.now():
            self.stderr.write(self.style.WARNING(
                "Seed slot dates are in the past; update race_start in jobs/management/commands/seed.py."
            ))
        # A shared future slot both Interviewing candidates can race for
        future1 = Slot.objects.create(employer=emp1, start_time=race_start, end_time=race_start + thirty)
        # A second future slot
        Slot.objects.create(employer=emp1, start_time=second_start, end_time=second_start + thirty)
        # A past slot (should not appear as bookable)
        Slot.objects.create(employer=emp1, start_time=past_start, end_time=past_start + thirty)

        self.stdout.write("Seeding a Demo Accepted application too (to cover status variety)...")
        # Give DataCorp one more application in Accepted state
        cand3 = User.objects.create_user(
            username="candidate_carol", email="carol@example.com",
            password="demo12345", role="candidate",
        )
        CandidateProfile.objects.create(
            user=cand3, display_name="Carol",
            skills=["Rust"], resume_text="Carol: Rust systems dev.",
        )
        Application.objects.create(
            candidate=cand3, job=job_b, status=Application.Status.ACCEPTED,
        )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Seed complete."))
        self.stdout.write("")
        self.stdout.write("Demo accounts (password: demo12345):")
        self.stdout.write("  employer_techco   / demo12345  (Employer — TechCo)")
        self.stdout.write("  employer_datacorp / demo12345  (Employer — DataCorp)")
        self.stdout.write("  candidate_alice   / demo12345  (Candidate — Python, SQL)")
        self.stdout.write("  candidate_bob     / demo12345  (Candidate — Python)")
        self.stdout.write("  candidate_carol   / demo12345  (Candidate — Rust)")
        self.stdout.write("")
        self.stdout.write("Two Interviewing candidates (alice, bob) share a future slot from TechCo.")
        self.stdout.write(f"Slot ID {future1.id} at {future1.start_time:%Y-%m-%d %H:%M} UTC — race it via the UI.")