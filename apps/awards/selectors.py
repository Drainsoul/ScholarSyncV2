from apps.awards.models import Award
from apps.programs.models import Program
from apps.students.models import StudentProfile


def holds_active_award(profile: StudentProfile, program: Program) -> bool:
    return Award.objects.filter(
        profile=profile, program=program, status=Award.Status.ACTIVE
    ).exists()


def other_active_awards(profile: StudentProfile, program: Program) -> list[Award]:
    return list(
        Award.objects.filter(profile=profile, status=Award.Status.ACTIVE)
        .exclude(program=program)
        .select_related("program")
        .order_by("program__name", "pk")
    )
