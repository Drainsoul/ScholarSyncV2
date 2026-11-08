"""Public program pages: what each program offers, before anyone signs in."""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_safe

from apps.programs import rules, selectors
from apps.programs.models import Program


@require_safe
def program_list(request: HttpRequest) -> HttpResponse:
    programs = Program.objects.filter(is_active=True)
    return render(request, "programs/list.html", {"programs": programs})


@require_safe
def program_detail(request: HttpRequest, slug: str) -> HttpResponse:
    program = get_object_or_404(
        Program.objects.prefetch_related("allowed_schools"), slug=slug, is_active=True
    )
    term = selectors.current_term()
    context = {
        "program": program,
        "rules": rules.rule_sentences(program),
        "term": term,
        "tiers": selectors.tiers_in_force(program, term) if term else [],
        "documents": selectors.required_documents_for(program, "new"),
    }
    return render(request, "programs/detail.html", context)
