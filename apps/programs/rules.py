"""A program's rules for new applicants, as plain sentences for the public pages."""

from apps.programs.models import Program, School

_TYPE_WORDS = {
    School.Type.PUBLIC: "public",
    School.Type.PRIVATE: "private",
    School.Type.SUC: "state university or college",
    School.Type.LCU: "local college or university",
}


def _join_or(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} or {items[-1]}"


def rule_sentences(program: Program) -> list[str]:
    sentences: list[str] = []
    if program.min_gwa_percent is not None:
        minimum = f"{program.min_gwa_percent.normalize():f}"
        sentences.append(f"A GWA of at least {minimum}% (schools that grade in percent).")
    if program.max_gwa_one_to_five is not None:
        sentences.append(
            f"A GWA of {program.max_gwa_one_to_five} or better (schools that grade 1 to 5)."
        )
    if program.min_units is not None:
        sentences.append(f"At least {program.min_units} units this term.")
    if program.min_residency_years is not None:
        years = program.min_residency_years
        unit = "year" if years == 1 else "years"
        sentences.append(f"Living in Taguig for at least {years} {unit}.")
    if program.requires_registered_voter:
        sentences.append("A registered voter of Taguig.")
    names = [school.name for school in program.allowed_schools.all()]
    if names:
        sentences.append(f"Studying at {_join_or(names)}.")
    if program.allowed_school_types:
        labels = [_TYPE_WORDS[School.Type(value)] for value in program.allowed_school_types]
        sentences.append(f"Studying at a {_join_or(labels)} school.")
    return sentences
