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