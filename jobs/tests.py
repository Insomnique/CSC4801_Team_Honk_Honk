from django.test import SimpleTestCase

from .matching import (
    candidate_job_sort_key,
    employer_applicant_sort_key,
    match_score,
    normalize_skills,
)

from datetime import timedelta
from django.utils import timezone

from django.db import IntegrityError

from django.test import TestCase
from django.urls import reverse
from accounts.models import User
from .models import Job, Application, Slot, Booking

def _slot_window(offset):
    """Start/end for a valid 30-minute slot, computed from one clock reading."""
    start = timezone.now() + offset
    return {"start_time": start, "end_time": start + timedelta(minutes=30)}

class NormalizeSkillsTests(SimpleTestCase):
    def test_trims_lowercases_dedupes(self):
        self.assertEqual(
            normalize_skills([" Python ", "python", "SQL", ""]),
            {"python", "sql"},
        )

    def test_none_and_empty(self):
        self.assertEqual(normalize_skills(None), set())
        self.assertEqual(normalize_skills([]), set())
        self.assertEqual(normalize_skills([None, "", "   "]), set())


class MatchScoreRequiredExamplesTests(SimpleTestCase):
    """The four examples required by FP-MATCH-1."""

    def test_full_match(self):
        self.assertEqual(match_score(["Python", "SQL"], ["Python", "SQL"]), 100)

    def test_half_match(self):
        self.assertEqual(match_score(["Python"], ["Python", "SQL"]), 50)

    def test_no_match(self):
        self.assertEqual(match_score(["Rust"], ["Python", "SQL"]), 0)

    def test_empty_required(self):
        self.assertEqual(match_score(["anything"], []), 100)


class MatchScoreEdgeCaseTests(SimpleTestCase):
    def test_floor_not_round(self):
        # 2 of 3 = 66.66..., floor to 66
        self.assertEqual(match_score(["a", "b"], ["a", "b", "c"]), 66)

    def test_normalization_applies(self):
        self.assertEqual(match_score([" PYTHON "], ["python"]), 100)

    def test_duplicates_in_required_dont_inflate(self):
        # Required with duplicates normalizes to {python}; candidate has python => 100
        self.assertEqual(match_score(["Python"], ["Python", "python", "PYTHON"]), 100)

    def test_empty_candidate_nonempty_required(self):
        self.assertEqual(match_score([], ["python"]), 0)

    def test_both_empty(self):
        self.assertEqual(match_score([], []), 100)

    def test_score_is_int_in_range(self):
        s = match_score(["a", "b", "c"], ["a", "b", "c", "d", "e"])
        self.assertIsInstance(s, int)
        self.assertGreaterEqual(s, 0)
        self.assertLessEqual(s, 100)


# --- Tie-breaker tests use lightweight stand-ins, no DB needed ---

class _FakeJob:
    def __init__(self, id, title):
        self.id = id
        self.title = title


class _FakeUser:
    def __init__(self, id, username):
        self.id = id
        self.username = username


class CandidateSortKeyTests(SimpleTestCase):
    def test_higher_score_first(self):
        jobs = [(_FakeJob(1, "A"), 80), (_FakeJob(2, "B"), 90)]
        pairs = [(score, job) for job, score in jobs]
        sorted_pairs = sorted(pairs, key=candidate_job_sort_key)
        self.assertEqual([j.id for _, j in sorted_pairs], [2, 1])

    def test_tie_broken_by_case_insensitive_title(self):
        pairs = [(50, _FakeJob(1, "banana")), (50, _FakeJob(2, "Apple"))]
        sorted_pairs = sorted(pairs, key=candidate_job_sort_key)
        self.assertEqual([j.title for _, j in sorted_pairs], ["Apple", "banana"])

    def test_tie_broken_by_stable_id(self):
        pairs = [(50, _FakeJob(3, "Same")), (50, _FakeJob(1, "same"))]
        sorted_pairs = sorted(pairs, key=candidate_job_sort_key)
        self.assertEqual([j.id for _, j in sorted_pairs], [1, 3])


class EmployerSortKeyTests(SimpleTestCase):
    def test_higher_score_first(self):
        pairs = [(80, _FakeUser(1, "alice")), (90, _FakeUser(2, "bob"))]
        sorted_pairs = sorted(pairs, key=employer_applicant_sort_key)
        self.assertEqual([u.username for _, u in sorted_pairs], ["bob", "alice"])

    def test_tie_broken_by_case_insensitive_name(self):
        pairs = [(50, _FakeUser(1, "Zoe")), (50, _FakeUser(2, "alice"))]
        sorted_pairs = sorted(pairs, key=employer_applicant_sort_key)
        self.assertEqual([u.username for _, u in sorted_pairs], ["alice", "Zoe"])

    def test_tie_broken_by_stable_id(self):
        pairs = [(50, _FakeUser(5, "Same")), (50, _FakeUser(2, "same"))]
        sorted_pairs = sorted(pairs, key=employer_applicant_sort_key)
        self.assertEqual([u.id for _, u in sorted_pairs], [2, 5])


from accounts.models import User
from .models import Job


class JobCrudTests(TestCase):
    def setUp(self):
        self.emp = User.objects.create_user(
            username="emp1", email="e1@e.com", password="pw", role="employer"
        )
        self.other_emp = User.objects.create_user(
            username="emp2", email="e2@e.com", password="pw", role="employer"
        )
        self.cand = User.objects.create_user(
            username="cand1", email="c1@e.com", password="pw", role="candidate"
        )

    def test_employer_can_create_job(self):
        self.client.login(username="emp1", password="pw")
        response = self.client.post(reverse("jobs:job_create"), {
            "title": "Backend Dev",
            "description": "Write code.",
            "required_skills": "Python, SQL",
        })
        self.assertEqual(response.status_code, 302)
        job = Job.objects.get(title="Backend Dev")
        self.assertEqual(job.employer, self.emp)
        self.assertEqual(job.required_skills, ["Python", "SQL"])

    def test_empty_title_rejected(self):
        self.client.login(username="emp1", password="pw")
        response = self.client.post(reverse("jobs:job_create"), {
            "title": "", "description": "x", "required_skills": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Job.objects.count(), 0)

    def test_employer_list_shows_only_own_jobs(self):
        Job.objects.create(employer=self.emp, title="MyOnlyJob", description="x")
        Job.objects.create(employer=self.other_emp, title="NotMineJob", description="x")
        self.client.login(username="emp1", password="pw")
        response = self.client.get(reverse("jobs:job_list"))
        self.assertContains(response, "MyOnlyJob")
        self.assertNotContains(response, "NotMineJob")

    def test_edit_own_job(self):
        job = Job.objects.create(employer=self.emp, title="Old", description="x")
        self.client.login(username="emp1", password="pw")
        response = self.client.post(reverse("jobs:job_edit", args=[job.pk]), {
            "title": "New", "description": "x", "required_skills": "",
        })
        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        self.assertEqual(job.title, "New")

    def test_edit_other_employers_job_403(self):
        job = Job.objects.create(employer=self.other_emp, title="X", description="x")
        self.client.login(username="emp1", password="pw")
        response = self.client.get(reverse("jobs:job_edit", args=[job.pk]))
        self.assertEqual(response.status_code, 403)

    def test_delete_own_empty_job_soft_deletes(self):
        job = Job.objects.create(employer=self.emp, title="X", description="x")
        self.client.login(username="emp1", password="pw")
        response = self.client.post(reverse("jobs:job_delete", args=[job.pk]))
        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        self.assertTrue(job.is_deleted)

    def test_delete_other_employers_job_403(self):
        job = Job.objects.create(employer=self.other_emp, title="X", description="x")
        self.client.login(username="emp1", password="pw")
        response = self.client.post(reverse("jobs:job_delete", args=[job.pk]))
        self.assertEqual(response.status_code, 403)

    def test_missing_job_returns_404(self):
        self.client.login(username="emp1", password="pw")
        response = self.client.get(reverse("jobs:job_edit", args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_candidate_cannot_access_employer_jobs(self):
        self.client.login(username="cand1", password="pw")
        response = self.client.get(reverse("jobs:job_list"))
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_redirected(self):
        response = self.client.get(reverse("jobs:job_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

class CandidateDashboardTests(TestCase):
    def setUp(self):
        self.cand = User.objects.create_user(
            username="candx", email="cx@e.com", password="pw", role="candidate"
        )
        self.emp = User.objects.create_user(
            username="empx", email="ex@e.com", password="pw", role="employer"
        )
        # Profile: Python, SQL
        from accounts.models import CandidateProfile
        CandidateProfile.objects.create(
            user=self.cand, display_name="Cand X", skills=["Python", "SQL"]
        )
        self.job_full = Job.objects.create(
            employer=self.emp, title="Full",
            description="d", required_skills=["Python", "SQL"],
        )
        self.job_half = Job.objects.create(
            employer=self.emp, title="Half",
            description="d", required_skills=["Python", "Rust"],
        )
        self.job_zero = Job.objects.create(
            employer=self.emp, title="Zero",
            description="d", required_skills=["Rust", "Go"],
        )

    def test_dashboard_sorts_by_score(self):
        self.client.login(username="candx", password="pw")
        response = self.client.get(reverse("jobs:candidate_dashboard"))
        self.assertEqual(response.status_code, 200)
        jobs_in_order = [item[1].title for item in response.context["scored"]]
        self.assertEqual(jobs_in_order, ["Full", "Half", "Zero"])
        scores = [item[0] for item in response.context["scored"]]
        self.assertEqual(scores, [100, 50, 0])

    def test_deleted_jobs_excluded(self):
        self.job_zero.is_deleted = True
        self.job_zero.save()
        self.client.login(username="candx", password="pw")
        response = self.client.get(reverse("jobs:candidate_dashboard"))
        titles = [item[1].title for item in response.context["scored"]]
        self.assertNotIn("Zero", titles)

    def test_employer_cannot_access_dashboard(self):
        self.client.login(username="empx", password="pw")
        response = self.client.get(reverse("jobs:candidate_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_job_detail_shows_score_for_candidate(self):
        self.client.login(username="candx", password="pw")
        response = self.client.get(reverse("jobs:job_detail", args=[self.job_full.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["score"], 100)

    def test_job_detail_404_for_deleted(self):
        self.job_zero.is_deleted = True
        self.job_zero.save()
        self.client.login(username="candx", password="pw")
        response = self.client.get(reverse("jobs:job_detail", args=[self.job_zero.pk]))
        self.assertEqual(response.status_code, 404)

    def test_dashboard_renders_score_in_html(self):
        self.client.login(username="candx", password="pw")
        response = self.client.get(reverse("jobs:candidate_dashboard"))
        self.assertContains(response, "Match: 100%")
        self.assertContains(response, "Match: 50%")
        self.assertContains(response, "Match: 0%")

from .models import Application


class ApplicationTests(TestCase):
    def setUp(self):
        self.cand = User.objects.create_user(
            username="acand", email="ac@e.com", password="pw", role="candidate"
        )
        self.other_cand = User.objects.create_user(
            username="bcand", email="bc@e.com", password="pw", role="candidate"
        )
        self.emp = User.objects.create_user(
            username="aemp", email="ae@e.com", password="pw", role="employer"
        )
        self.job = Job.objects.create(
            employer=self.emp, title="Dev", description="d",
            required_skills=["Python"],
        )

    def test_candidate_can_apply(self):
        self.client.login(username="acand", password="pw")
        response = self.client.post(reverse("jobs:apply_to_job", args=[self.job.pk]))
        self.assertEqual(response.status_code, 302)
        app = Application.objects.get(candidate=self.cand, job=self.job)
        self.assertEqual(app.status, "pending")

    def test_duplicate_apply_returns_409(self):
        self.client.login(username="acand", password="pw")
        self.client.post(reverse("jobs:apply_to_job", args=[self.job.pk]))
        response = self.client.post(reverse("jobs:apply_to_job", args=[self.job.pk]))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            Application.objects.filter(candidate=self.cand, job=self.job).count(), 1
        )

    def test_employer_cannot_apply(self):
        self.client.login(username="aemp", password="pw")
        response = self.client.post(reverse("jobs:apply_to_job", args=[self.job.pk]))
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_redirected(self):
        response = self.client.post(reverse("jobs:apply_to_job", args=[self.job.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_apply_to_deleted_job_404(self):
        self.job.is_deleted = True
        self.job.save()
        self.client.login(username="acand", password="pw")
        response = self.client.post(reverse("jobs:apply_to_job", args=[self.job.pk]))
        self.assertEqual(response.status_code, 404)

    def test_my_applications_shows_only_own(self):
        Application.objects.create(candidate=self.cand, job=self.job)
        Application.objects.create(candidate=self.other_cand, job=self.job)
        self.client.login(username="acand", password="pw")
        response = self.client.get(reverse("jobs:my_applications"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["apps"]), 1)
        self.assertEqual(response.context["apps"][0].candidate, self.cand)

    def test_employer_cannot_see_my_applications(self):
        self.client.login(username="aemp", password="pw")
        response = self.client.get(reverse("jobs:my_applications"))
        self.assertEqual(response.status_code, 403)

    def test_delete_job_with_application_returns_409(self):
        Application.objects.create(candidate=self.cand, job=self.job)
        self.client.login(username="aemp", password="pw")
        response = self.client.post(reverse("jobs:job_delete", args=[self.job.pk]))
        self.assertEqual(response.status_code, 409)
        self.job.refresh_from_db()
        self.assertFalse(self.job.is_deleted)

class ApplicantManagementTests(TestCase):
    def setUp(self):
        from accounts.models import CandidateProfile

        self.emp = User.objects.create_user(username="mgr", email="m@e.com", password="pw", role="employer")
        self.other_emp = User.objects.create_user(username="mgr2", email="m2@e.com", password="pw", role="employer")

        # Candidates: Alice (Python, SQL), Bob (Python), Charlie (Rust), Dave (Python, SQL) for tie test
        self.alice = User.objects.create_user(username="alice", email="a@e.com", password="pw", role="candidate")
        CandidateProfile.objects.create(user=self.alice, display_name="Alice", skills=["Python", "SQL"])
        self.bob = User.objects.create_user(username="bob", email="b@e.com", password="pw", role="candidate")
        CandidateProfile.objects.create(user=self.bob, display_name="Bob", skills=["Python"])
        self.charlie = User.objects.create_user(username="charlie", email="c@e.com", password="pw", role="candidate")
        CandidateProfile.objects.create(user=self.charlie, display_name="Charlie", skills=["Rust"])
        self.dave = User.objects.create_user(username="dave", email="d@e.com", password="pw", role="candidate")
        CandidateProfile.objects.create(user=self.dave, display_name="dave", skills=["Python", "SQL"])

        self.job = Job.objects.create(
            employer=self.emp, title="Dev", description="d",
            required_skills=["Python", "SQL"],
        )
        for u in (self.alice, self.bob, self.charlie, self.dave):
            Application.objects.create(candidate=u, job=self.job)

    def test_applicants_sorted_by_score_then_name(self):
        self.client.login(username="mgr", password="pw")
        response = self.client.get(reverse("jobs:job_applicants", args=[self.job.pk]))
        self.assertEqual(response.status_code, 200)
        names = [app.candidate.candidate_profile.display_name for _, app in response.context["scored"]]
        # Alice and Dave both 100 (tie), Alice before Dave (ci). Bob 50, Charlie 0.
        self.assertEqual(names, ["Alice", "dave", "Bob", "Charlie"])

    def test_scores_reflect_skills(self):
        self.client.login(username="mgr", password="pw")
        response = self.client.get(reverse("jobs:job_applicants", args=[self.job.pk]))
        scores = {app.candidate.username: s for s, app in response.context["scored"]}
        self.assertEqual(scores["alice"], 100)
        self.assertEqual(scores["bob"], 50)
        self.assertEqual(scores["charlie"], 0)

    def test_other_employer_cannot_view_applicants(self):
        self.client.login(username="mgr2", password="pw")
        response = self.client.get(reverse("jobs:job_applicants", args=[self.job.pk]))
        self.assertEqual(response.status_code, 403)

    def test_candidate_cannot_view_applicants(self):
        self.client.login(username="alice", password="pw")
        response = self.client.get(reverse("jobs:job_applicants", args=[self.job.pk]))
        self.assertEqual(response.status_code, 403)

    def test_employer_can_update_status(self):
        app_obj = Application.objects.get(candidate=self.alice, job=self.job)
        self.client.login(username="mgr", password="pw")
        for status in ("interviewing", "rejected", "accepted", "pending"):
            response = self.client.post(
                reverse("jobs:update_application_status", args=[app_obj.pk]),
                {"status": status},
            )
            self.assertEqual(response.status_code, 302)
            app_obj.refresh_from_db()
            self.assertEqual(app_obj.status, status)

    def test_invalid_status_rejected(self):
        app_obj = Application.objects.get(candidate=self.alice, job=self.job)
        self.client.login(username="mgr", password="pw")
        response = self.client.post(
            reverse("jobs:update_application_status", args=[app_obj.pk]),
            {"status": "bogus"},
        )
        self.assertEqual(response.status_code, 400)
        app_obj.refresh_from_db()
        self.assertEqual(app_obj.status, "pending")

    def test_other_employer_cannot_update_status(self):
        app_obj = Application.objects.get(candidate=self.alice, job=self.job)
        self.client.login(username="mgr2", password="pw")
        response = self.client.post(
            reverse("jobs:update_application_status", args=[app_obj.pk]),
            {"status": "accepted"},
        )
        self.assertEqual(response.status_code, 403)
        app_obj.refresh_from_db()
        self.assertEqual(app_obj.status, "pending")

    def test_candidate_cannot_update_status(self):
        app_obj = Application.objects.get(candidate=self.alice, job=self.job)
        self.client.login(username="alice", password="pw")
        response = self.client.post(
            reverse("jobs:update_application_status", args=[app_obj.pk]),
            {"status": "accepted"},
        )
        self.assertEqual(response.status_code, 403)
        app_obj.refresh_from_db()
        self.assertEqual(app_obj.status, "pending")



class SlotTests(TestCase):
    def setUp(self):
        self.emp = User.objects.create_user(
            username="semp", email="s@e.com", password="pw", role="employer"
        )
        self.other_emp = User.objects.create_user(
            username="semp2", email="s2@e.com", password="pw", role="employer"
        )
        self.cand = User.objects.create_user(
            username="scand", email="sc@e.com", password="pw", role="candidate"
        )

    def _future_dt(self, minutes=60):
        return (timezone.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M")

    def test_employer_can_create_future_slot(self):
        self.client.login(username="semp", password="pw")
        response = self.client.post(reverse("jobs:slot_create"), {
            "start_time": self._future_dt(60),
        })
        self.assertEqual(response.status_code, 302)
        slot = Slot.objects.get(employer=self.emp)
        self.assertEqual(slot.duration_minutes, 30)
        self.assertTrue(slot.is_future())

    def test_past_start_rejected(self):
        self.client.login(username="semp", password="pw")
        past = (timezone.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(reverse("jobs:slot_create"), {"start_time": past})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Slot.objects.count(), 0)

    def test_delete_own_slot(self):
        slot = Slot.objects.create(
            employer=self.emp,
            **_slot_window(timedelta(hours=1)),
        )
        self.client.login(username="semp", password="pw")
        response = self.client.post(reverse("jobs:slot_delete", args=[slot.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Slot.objects.filter(pk=slot.pk).exists())

    def test_delete_other_employers_slot_403(self):
        slot = Slot.objects.create(
            employer=self.other_emp,
            **_slot_window(timedelta(hours=1)),
        )
        self.client.login(username="semp", password="pw")
        response = self.client.post(reverse("jobs:slot_delete", args=[slot.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Slot.objects.filter(pk=slot.pk).exists())

    def test_other_employer_slots_not_listed(self):
        Slot.objects.create(
            employer=self.emp,
            **_slot_window(timedelta(hours=1)),
        )
        Slot.objects.create(
            employer=self.other_emp,
            **_slot_window(timedelta(hours=2)),
        )
        self.client.login(username="semp", password="pw")
        response = self.client.get(reverse("jobs:slot_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["slots"]), 1)

    def test_candidate_cannot_manage_slots(self):
        self.client.login(username="scand", password="pw")
        self.assertEqual(self.client.get(reverse("jobs:slot_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("jobs:slot_create")).status_code, 403)


class BookingEligibilityTests(TestCase):
    def setUp(self):
        from accounts.models import CandidateProfile
        self.emp = User.objects.create_user(username="bemp", email="be@e.com", password="pw", role="employer")
        self.other_emp = User.objects.create_user(username="bemp2", email="be2@e.com", password="pw", role="employer")
        self.cand = User.objects.create_user(username="bcand", email="bc@e.com", password="pw", role="candidate")
        CandidateProfile.objects.create(user=self.cand, skills=["Python"])
        self.other_cand = User.objects.create_user(username="bcand2", email="bc2@e.com", password="pw", role="candidate")
        CandidateProfile.objects.create(user=self.other_cand, skills=["Python"])
        self.job = Job.objects.create(employer=self.emp, title="J", description="d", required_skills=[])
        self.other_job = Job.objects.create(employer=self.other_emp, title="OJ", description="d", required_skills=[])
        self.app = Application.objects.create(candidate=self.cand, job=self.job, status="interviewing")
        self.other_app = Application.objects.create(candidate=self.other_cand, job=self.job, status="interviewing")
        self.slot = Slot.objects.create(
            employer=self.emp,
            **_slot_window(timedelta(hours=1)),
        )

    def test_eligible_booking_created(self):
        self.client.login(username="bcand", password="pw")
        response = self.client.post(reverse("jobs:book_slot", args=[self.slot.pk]), {"application_pk": self.app.pk})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Booking.objects.filter(application=self.app, slot=self.slot).exists())

    def test_non_numeric_application_id_returns_404(self):
        self.client.login(username="bcand", password="pw")
        for bad in ("abc", "", "1 OR 1=1"):
            with self.subTest(application_pk=bad):
                response = self.client.post(reverse("jobs:book_slot", args=[self.slot.pk]), {"application_pk": bad})
                self.assertEqual(response.status_code, 404)
        self.assertFalse(Booking.objects.exists())

    def test_booking_using_other_candidates_application_403(self):
        self.client.login(username="bcand", password="pw")
        response = self.client.post(reverse("jobs:book_slot", args=[self.slot.pk]), {"application_pk": self.other_app.pk})
        self.assertEqual(response.status_code, 403)

    def test_slot_from_other_employer_403(self):
        other_slot = Slot.objects.create(
            employer=self.other_emp,
            **_slot_window(timedelta(hours=1)),
        )
        self.client.login(username="bcand", password="pw")
        response = self.client.post(reverse("jobs:book_slot", args=[other_slot.pk]), {"application_pk": self.app.pk})
        self.assertEqual(response.status_code, 403)

    def test_non_interviewing_application_409(self):
        self.app.status = "pending"
        self.app.save()
        self.client.login(username="bcand", password="pw")
        response = self.client.post(reverse("jobs:book_slot", args=[self.slot.pk]), {"application_pk": self.app.pk})
        self.assertEqual(response.status_code, 409)

    def test_past_slot_409(self):
        past = Slot.objects.create(
            employer=self.emp,
            **_slot_window(-timedelta(hours=1)),
        )
        self.client.login(username="bcand", password="pw")
        response = self.client.post(reverse("jobs:book_slot", args=[past.pk]), {"application_pk": self.app.pk})
        self.assertEqual(response.status_code, 409)

    def test_already_booked_application_409(self):
        other_slot = Slot.objects.create(
            employer=self.emp,
            **_slot_window(timedelta(hours=2)),
        )
        Booking.objects.create(application=self.app, slot=self.slot)
        self.client.login(username="bcand", password="pw")
        response = self.client.post(reverse("jobs:book_slot", args=[other_slot.pk]), {"application_pk": self.app.pk})
        self.assertEqual(response.status_code, 409)

    def test_slot_already_booked_by_other_409(self):
        Booking.objects.create(application=self.other_app, slot=self.slot)
        self.client.login(username="bcand", password="pw")
        response = self.client.post(reverse("jobs:book_slot", args=[self.slot.pk]), {"application_pk": self.app.pk})
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "Slot already booked", status_code=409)
        self.assertEqual(Booking.objects.filter(slot=self.slot).count(), 1)

    def test_delete_booked_slot_409(self):
        Booking.objects.create(application=self.app, slot=self.slot)
        self.client.login(username="bemp", password="pw")
        response = self.client.post(reverse("jobs:slot_delete", args=[self.slot.pk]))
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Slot.objects.filter(pk=self.slot.pk).exists())

    def test_booking_remains_after_status_change(self):
        Booking.objects.create(application=self.app, slot=self.slot)
        self.app.status = "accepted"
        self.app.save()
        self.assertEqual(Booking.objects.filter(application=self.app).count(), 1)
        self.assertTrue(self.slot.is_booked())

    def test_bookable_slots_page_loads(self):
        self.client.login(username="bcand", password="pw")
        response = self.client.get(reverse("jobs:bookable_slots", args=[self.app.pk]))
        self.assertEqual(response.status_code, 200)


class AtomicityTests(TestCase):
    """FP-SCHED-3: DB-level constraint, not application-level check."""

    def setUp(self):
        self.emp = User.objects.create_user(username="aemp3", email="ae3@e.com", password="pw", role="employer")
        self.c1 = User.objects.create_user(username="ac1", email="ac1@e.com", password="pw", role="candidate")
        self.c2 = User.objects.create_user(username="ac2", email="ac2@e.com", password="pw", role="candidate")
        self.job = Job.objects.create(employer=self.emp, title="J", description="d", required_skills=[])
        self.app1 = Application.objects.create(candidate=self.c1, job=self.job, status="interviewing")
        self.app2 = Application.objects.create(candidate=self.c2, job=self.job, status="interviewing")
        self.slot = Slot.objects.create(
            employer=self.emp,
            **_slot_window(timedelta(hours=1)),
        )

    def test_concurrent_double_booking_one_wins(self):
        Booking.objects.create(application=self.app1, slot=self.slot)
        from django.db import transaction
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Booking.objects.create(application=self.app2, slot=self.slot)
        self.assertEqual(Booking.objects.filter(slot=self.slot).count(), 1)


class SecurityTests(TestCase):
    def setUp(self):
        from accounts.models import CandidateProfile
        self.emp = User.objects.create_user(username="sec_emp", email="se@e.com", password="pw", role="employer")
        self.cand = User.objects.create_user(username="sec_cand", email="sc@e.com", password="pw", role="candidate")
        CandidateProfile.objects.create(user=self.cand, display_name="Sec Cand", skills=["Python"])

    def test_sql_injection_is_bound_not_executed(self):
        """FP-SEC-2: SQL metacharacters are stored as literal data."""
        self.client.login(username="sec_emp", password="pw")
        payload = "'; DROP TABLE jobs_job; --"
        response = self.client.post(reverse("jobs:job_create"), {
            "title": payload,
            "description": "test",
            "required_skills": "",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Job.objects.count(), 1)
        job = Job.objects.get()
        self.assertEqual(job.title, payload)

    def test_xss_payload_is_escaped(self):
        """FP-SEC-3: <script> is escaped in rendered HTML."""
        self.client.login(username="sec_emp", password="pw")
        payload = "<script>alert(1)</script>"
        self.client.post(reverse("jobs:job_create"), {
            "title": payload,
            "description": "test",
            "required_skills": "",
        })
        job = Job.objects.get()
        self.client.logout()

        self.client.login(username="sec_cand", password="pw")
        response = self.client.get(reverse("jobs:job_detail", args=[job.pk]))
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_candidate_sees_own_profile_not_others(self):
        """FP-SEC-1: candidate cannot read another candidate's resume."""
        from accounts.models import CandidateProfile
        other = User.objects.create_user(username="sec_cand2", email="sc2@e.com", password="pw", role="candidate")
        CandidateProfile.objects.create(user=other, display_name="Other", skills=["Rust"], resume_text="secret resume")

        self.client.login(username="sec_cand", password="pw")
        response = self.client.get(reverse("accounts:candidate_profile"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "secret resume")
        self.assertNotContains(response, "Other")

    def test_employer_cannot_view_candidate_profile_url(self):
        """FP-SEC-1: employer hitting candidate profile URL gets 403."""
        self.client.login(username="sec_emp", password="pw")
        response = self.client.get(reverse("accounts:candidate_profile"))
        self.assertEqual(response.status_code, 403)

class SlotValidationTests(TestCase):
    """FP-SCHED-1: invalid durations and end-before-start are rejected by the database."""
 
    def setUp(self):
        self.emp = User.objects.create_user(username="vemp", email="ve@e.com", password="pw", role="employer")
        self.start = timezone.now() + timedelta(days=1)
 
    def test_valid_30_minute_slot_accepted(self):
        Slot.objects.create(employer=self.emp, start_time=self.start, end_time=self.start + timedelta(minutes=30))
        self.assertEqual(Slot.objects.count(), 1)
 
    def test_non_30_minute_slot_rejected(self):
        from django.db import transaction
        for minutes in (15, 29, 31, 45, 60):
            with self.subTest(minutes=minutes):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        Slot.objects.create(
                            employer=self.emp, start_time=self.start,
                            end_time=self.start + timedelta(minutes=minutes),
                        )
        self.assertEqual(Slot.objects.count(), 0)
 
    def test_end_before_start_rejected(self):
        from django.db import transaction
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Slot.objects.create(
                    employer=self.emp, start_time=self.start,
                    end_time=self.start - timedelta(minutes=30),
                )
        self.assertEqual(Slot.objects.count(), 0)

    def test_overlapping_slot_rejected(self):
        start = self.start.replace(second=0, microsecond=0)   # the form only takes whole minutes
        Slot.objects.create(employer=self.emp, start_time=start, end_time=start + timedelta(minutes=30))
        self.client.login(username="vemp", password="pw")
        overlap = (start + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(reverse("jobs:slot_create"), {"start_time": overlap})
        self.assertEqual(response.status_code, 200)            # form shown again with the error
        self.assertContains(response, "overlaps with a slot you already created")
        self.assertEqual(Slot.objects.filter(employer=self.emp).count(), 1)
 
    def test_back_to_back_slot_allowed(self):
        start = self.start.replace(second=0, microsecond=0)   # the form only takes whole minutes
        Slot.objects.create(employer=self.emp, start_time=start, end_time=start + timedelta(minutes=30))
        self.client.login(username="vemp", password="pw")
        nxt = (start + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M")
        self.client.post(reverse("jobs:slot_create"), {"start_time": nxt})
        self.assertEqual(Slot.objects.filter(employer=self.emp).count(), 2)

    def test_slot_form_shows_utc(self):
        self.client.login(username="vemp", password="pw")
        response = self.client.get(reverse("jobs:slot_create"))
        self.assertContains(response, "UTC")
 
 
class BookingVisibilityTests(TestCase):
    """FP-SCHED-1/2, FP-CAN-3, FP-EMP-3: booked slots hidden; booking visible to both sides."""
 
    def setUp(self):
        from accounts.models import CandidateProfile
        self.emp = User.objects.create_user(username="vis_emp", email="ve2@e.com", password="pw", role="employer")
        self.c1 = User.objects.create_user(username="vis_c1", email="v1@e.com", password="pw", role="candidate")
        self.c2 = User.objects.create_user(username="vis_c2", email="v2@e.com", password="pw", role="candidate")
        CandidateProfile.objects.create(user=self.c1, display_name="Vis One", skills=["Python"])
        CandidateProfile.objects.create(user=self.c2, display_name="Vis Two", skills=["Python"])
        self.job = Job.objects.create(employer=self.emp, title="VJ", description="d", required_skills=["Python"])
        self.app1 = Application.objects.create(candidate=self.c1, job=self.job, status="interviewing")
        self.app2 = Application.objects.create(candidate=self.c2, job=self.job, status="interviewing")
        start = (timezone.now() + timedelta(days=3)).replace(second=0, microsecond=0)
        self.slot = Slot.objects.create(employer=self.emp, start_time=start, end_time=start + timedelta(minutes=30))
        self.free = Slot.objects.create(
            employer=self.emp, start_time=start + timedelta(hours=1),
            end_time=start + timedelta(hours=1, minutes=30),
        )
        self.when = start.strftime("%Y-%m-%d %H:%M")
 
    def test_booked_slot_not_shown_as_available(self):
        Booking.objects.create(application=self.app1, slot=self.slot)
        self.client.login(username="vis_c2", password="pw")
        response = self.client.get(reverse("jobs:bookable_slots", args=[self.app2.pk]))
        self.assertEqual(response.status_code, 200)
        listed = list(response.context["slots"])
        self.assertNotIn(self.slot, listed)
        self.assertIn(self.free, listed)
 
    def test_employer_applicant_list_shows_booking(self):
        Booking.objects.create(application=self.app1, slot=self.slot)
        self.client.login(username="vis_emp", password="pw")
        response = self.client.get(reverse("jobs:job_applicants", args=[self.job.pk]))
        self.assertContains(response, "Interview (UTC)")
        self.assertContains(response, self.when)
 
    def test_applicants_table_partial_shows_booking(self):
        # The employer pages load the applicant list with fetch(); that partial must show the booking too.
        Booking.objects.create(application=self.app1, slot=self.slot)
        self.client.login(username="vis_emp", password="pw")
        response = self.client.get(
            reverse("jobs:job_applicants", args=[self.job.pk]), HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertTemplateUsed(response, "jobs/_applicants_table.html")
        self.assertContains(response, "Interview (UTC)")
        self.assertContains(response, self.when)

    def test_candidate_sees_booking_after_leaving_interviewing(self):
        Booking.objects.create(application=self.app1, slot=self.slot)
        self.app1.status = "accepted"
        self.app1.save()
        self.client.login(username="vis_c1", password="pw")
        response = self.client.get(reverse("jobs:my_applications"))
        self.assertContains(response, f"Booked: {self.when}")
        # The slot stays unavailable to others.
        self.client.login(username="vis_c2", password="pw")
        response = self.client.get(reverse("jobs:bookable_slots", args=[self.app2.pk]))
        self.assertNotIn(self.slot, list(response.context["slots"]))
 
 
class SeedCommandTests(TestCase):
    """FP-DOC-3: the seed command is deterministic and covers the required data."""
 
    def _seed(self):
        from io import StringIO
        from django.core.management import call_command
        call_command("seed", stdout=StringIO(), stderr=StringIO())
 
    def test_seed_covers_required_data(self):
        self._seed()
        self.assertGreaterEqual(User.objects.filter(role="candidate").count(), 2)
        self.assertGreaterEqual(User.objects.filter(role="employer").count(), 2)
        self.assertTrue(Job.objects.filter(required_skills=[]).exists())
        self.assertEqual(            
            set(Application.objects.values_list("status", flat=True)),
            {"pending", "interviewing", "rejected", "accepted"},
        )
        self.assertGreaterEqual(Application.objects.filter(status="interviewing").count(), 2)
        self.assertTrue(Slot.objects.filter(start_time__gt=timezone.now(), booking__isnull=True).exists())
 
    def test_seed_is_repeatable(self):
        self._seed()
        first = sorted(Slot.objects.values_list("id", "start_time"))
        first_jobs = sorted(Job.objects.values_list("id", "title"))
        self._seed()
        self.assertEqual(sorted(Slot.objects.values_list("id", "start_time")), first)
        self.assertEqual(sorted(Job.objects.values_list("id", "title")), first_jobs)