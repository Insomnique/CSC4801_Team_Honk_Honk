def normalize_skills(skills):
    """Trim, lowercase, drop empties, dedupe. Returns a set of strings."""
    if not skills:
        return set()
    normalized = set()
    for s in skills:
        if s is None:
            continue
        cleaned = str(s).strip().lower()
        if cleaned:
            normalized.add(cleaned)
    return normalized


def match_score(candidate_skills, required_skills) -> int:
    """
    Deterministic skill-overlap score from 0 to 100.
    score = 100                                   if required is empty
    score = floor(100 * |C ∩ R| / |R|)            otherwise
    """
    C = normalize_skills(candidate_skills)
    R = normalize_skills(required_skills)
    if len(R) == 0:
        return 100
    return (100 * len(C & R)) // len(R)


def candidate_job_sort_key(job_with_score):
    """Sort key for the candidate dashboard: highest score, then title (ci), then stable job id."""
    score, job = job_with_score
    return (-score, job.title.lower(), job.id)


def employer_applicant_sort_key(applicant_with_score):
    score, user = applicant_with_score
    name = (getattr(user, "display_name", "") or user.username).lower()
    return (-score, name, user.id)