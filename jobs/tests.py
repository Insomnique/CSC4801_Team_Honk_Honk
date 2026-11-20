from django.test import SimpleTestCase

from .matching import (
    candidate_job_sort_key,
    employer_applicant_sort_key,
    match_score,
    normalize_skills,
)

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

from django.test import TestCase
from django.urls import reverse

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