from apps.awards.models import Award
from apps.programs.models import Program
from apps.students.models import StudentProfile


def holds_award(profile: StudentProfile, program: Program) -> bool:
    """An active award, or one on hold: either way the student holds the scholarship."""
    return Award.objects.filter(
        profile=profile, program=program, status__in=Award.HELD_STATUSES
    ).exists()


def other_active_awards(profile: StudentProfile, program: Program) -> list[Award]:
    return list(
        Award.objects.filter(profile=profile, status=Award.Status.ACTIVE)
        .exclude(program=program)
        .select_related("program")
        .order_by("program__name", "pk")
    )
