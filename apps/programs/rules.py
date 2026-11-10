"""A program's rules for new applicants, as plain sentences for the public pages."""

from collections.abc import Sequence

from django.utils.dateformat import format as format_date

from apps.programs.models import Program, School

TYPE_WORDS = {
    School.Type.PUBLIC: "public",
    School.Type.PRIVATE: "private",
    School.Type.SUC: "state university or college",
    School.Type.LCU: "local college or university",
}


def join_or(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} or {items[-1]}"


def _percent_sentence(program: Program) -> str:
    assert program.min_gwa_percent is not None
    minimum = f"{program.min_gwa_percent.normalize():f}"
    return f"A GWA of at least {minimum}% (schools that grade in percent)."


def _one_to_five_sentence(program: Program) -> str:
    return f"A GWA of {program.max_gwa_one_to_five} or better (schools that grade 1 to 5)."


def _gwa_sentences(program: Program) -> list[str]:
    sentences: list[str] = []
    if program.min_gwa_percent is not None:
        sentences.append(_percent_sentence(program))
    if program.max_gwa_one_to_five is not None:
        sentences.append(_one_to_five_sentence(program))
    return sentences


def rule_sentence(
    program: Program, code: str, *, allowed_schools: Sequence[School] | None = None
) -> str:
    """The sentence for one rule code ("" if the program has no such rule).

    Codes match the eligibility checks. Pass ``allowed_schools`` to avoid a query.
    """
    if code == "gwa":
        return " ".join(_gwa_sentences(program))
    if code == "units":
        if program.min_units is None:
            return ""
        return f"At least {program.min_units} units this term."
    if code == "residency":
        if program.min_residency_years is None:
            return ""
        years = program.min_residency_years
        unit = "year" if years == 1 else "years"
        return f"Living in Taguig for at least {years} {unit}."
    if code == "voter":
        return "A registered voter of Taguig." if program.requires_registered_voter else ""
    if code == "allowed_schools":
        schools = program.allowed_schools.all() if allowed_schools is None else allowed_schools
        names = [school.name for school in schools]
        return f"Studying at {join_or(names)}." if names else ""
    if code == "school_type":
        if not program.allowed_school_types:
            return ""
        labels = [TYPE_WORDS[School.Type(value)] for value in program.allowed_school_types]
        return f"Studying at a {join_or(labels)} school."
    if code == "window":
        # Neutral wording: it also heads the unmet row ("Applications closed on ...").
        if program.applications_close_on is None:
            return "Applications must be open."
        closes = format_date(program.applications_close_on, "j F Y")
        return f"Applications must be open (they close on {closes})."
    if code == "school":
        return "You have a current school in your profile."
    raise ValueError(f"Unknown rule code: {code}")


def rule_sentences(program: Program) -> list[str]:
    sentences = _gwa_sentences(program)
    for code in ("units", "residency", "voter", "allowed_schools", "school_type"):
        sentence = rule_sentence(program, code)
        if sentence:
            sentences.append(sentence)
    return sentences
