"""Staff money screens: schedules, disbursements and the budget. Views are thin."""

from typing import Any

from allauth.account.decorators import reauthentication_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from apps.accounts.models import User
from apps.core.permissions import ProgramStaffRequiredMixin
from apps.core.shell import shell_context
from apps.money import selectors, services
from apps.money.forms import BudgetForm, BulkForm, RejectForm, ScheduleForm
from apps.money.models import Disbursement, DistributionSchedule
from apps.programs.models import Program, ProgramMembership

PAGE_SIZE = 25
RELEASE_ACTIONS = frozenset({"release", "release_all"})
STATUS_TONES: dict[str, str] = {
    Disbursement.Status.PENDING: "neutral",
    Disbursement.Status.APPROVED: "info",
    Disbursement.Status.RELEASED: "success",
    Disbursement.Status.REJECTED: "danger",
}


def _plural(count: int, word: str = "payout") -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _actor(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)  # the staff mixin has signed them in
    return user


def _error_text(error: ValidationError) -> str:
    return " ".join(error.messages)


def money_tabs(program: Program, active: str) -> list[dict[str, object]]:
    """The "Money sections" tabs (the approved mockup)."""
    tabs = [
        ("schedules", "Schedules", reverse("money:schedules", args=[program.slug])),
        ("disbursements", "Disbursements", reverse("money:overview", args=[program.slug])),
        ("budget", "Budget", reverse("money:budget", args=[program.slug])),
    ]
    return [
        {"label": label, "url": url, "current": key == active, "count": 0}
        for key, label, url in tabs
    ]


def _page(request: HttpRequest, program: Program, active: str, **extra: Any) -> dict[str, Any]:
    return {
        **shell_context(request, area="staff", program=program),
        "money_tabs": money_tabs(program, active),
        **extra,
    }


class SchedulesView(ProgramStaffRequiredMixin, View):
    def get(self, request: HttpRequest, program: str) -> HttpResponse:
        context = _page(
            request,
            self.program,
            "schedules",
            schedules=selectors.schedule_list(self.program),
        )
        return render(request, "money/schedules.html", context)


class ScheduleFormView(ProgramStaffRequiredMixin, View):
    """New schedule (no pk) or edit one."""

    def _render(
        self,
        request: HttpRequest,
        form: ScheduleForm,
        schedule: DistributionSchedule | None,
        status: int = 200,
    ) -> HttpResponse:
        context = _page(request, self.program, "schedules", form=form, schedule=schedule)
        return render(request, "money/schedule_form.html", context, status=status)

    def get(self, request: HttpRequest, program: str, pk: int | None = None) -> HttpResponse:
        schedule = selectors.staff_schedule(self.program, pk) if pk is not None else None
        initial = ScheduleForm.initial_for(schedule) if schedule is not None else None
        return self._render(request, ScheduleForm(initial=initial, program=self.program), schedule)

    def post(self, request: HttpRequest, program: str, pk: int | None = None) -> HttpResponse:
        schedule = selectors.staff_schedule(self.program, pk) if pk is not None else None
        form = ScheduleForm(request.POST, program=self.program)
        if not form.is_valid():
            return self._render(request, form, schedule, status=400)
        data = services.ScheduleData(**form.cleaned_data)
        try:
            services.save_schedule(
                actor=_actor(request),
                program=self.program,
                schedule_id=pk,
                data=data,
                request=request,
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self._render(request, form, schedule, status=400)
        messages.success(request, "Schedule saved.")
        return redirect("money:schedules", program=self.program.slug)


class SchedulePublishView(ProgramStaffRequiredMixin, View):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, program: str, pk: int) -> HttpResponse:
        published = request.POST.get("publish") == "1"
        try:
            services.set_published(
                actor=_actor(request),
                program=self.program,
                schedule_id=pk,
                published=published,
                request=request,
            )
        except ValidationError as error:
            messages.warning(request, _error_text(error))
        else:
            messages.success(
                request,
                "Published. Scholars can see this schedule." if published else "Unpublished.",
            )
        return redirect("money:schedules", program=self.program.slug)


def _can_decide(membership: ProgramMembership | None) -> bool:
    """Heads and the office (no membership) approve, reject, release and revert."""
    return membership is None or membership.level == ProgramMembership.Level.HEAD


def _back(program: Program, schedule_id: int) -> HttpResponse:
    return redirect("money:schedule", program=program.slug, schedule=schedule_id)


class OverviewView(ProgramStaffRequiredMixin, View):
    def get(self, request: HttpRequest, program: str) -> HttpResponse:
        context = _page(
            request,
            self.program,
            "disbursements",
            schedules=selectors.schedule_list(self.program),
        )
        return render(request, "money/overview.html", context)


class ScheduleView(ProgramStaffRequiredMixin, View):
    def get(self, request: HttpRequest, program: str, schedule: int) -> HttpResponse:
        found = selectors.staff_schedule(self.program, schedule)
        filters = selectors.parse_row_filters(request.GET, self.program)
        page = Paginator(selectors.schedule_rows(found, filters), PAGE_SIZE).get_page(
            request.GET.get("page")
        )
        rows = []
        for row in page.object_list:
            flag = ""
            if row.status == Disbursement.Status.PENDING:
                flag = selectors.ineligible_reason(row.scholar_term)
            rows.append(
                {
                    "row": row,
                    "tier": row.scholar_term.tier or row.scholar_term.award.tier,
                    "tone": STATUS_TONES[row.status],
                    "flag": flag,
                }
            )
        totals = selectors.schedule_totals(found)
        tiers = (
            self.program.tiers.order_by("sort_order", "name").values_list("code", "name").distinct()
        )
        context = _page(
            request,
            self.program,
            "disbursements",
            schedule=found,
            page=page,
            rows=rows,
            filters=filters,
            statuses=Disbursement.Status.choices,
            tiers=list(dict(tiers).items()),
            figures=selectors.budget_figures(
                selectors.budget_summary(self.program, found.distribution_date.year)
            ),
            prepared_count=totals[Disbursement.Status.PENDING][0],
            approved_count=totals[Disbursement.Status.APPROVED][0],
            can_decide=_can_decide(self.membership),
        )
        return render(request, "money/schedule.html", context)


class GenerateView(ProgramStaffRequiredMixin, View):
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, program: str, schedule: int) -> HttpResponse:
        result = services.generate(
            actor=_actor(request), program=self.program, schedule_id=schedule, request=request
        )
        messages.success(request, f"Generated {_plural(result.created, 'disbursement')}.")
        if result.refreshed:
            messages.info(request, f"Recalculated {_plural(result.refreshed, 'prepared payout')}.")
        skips = [
            (result.not_active, "on hold or ended"),
            (result.incomplete, "with documents not checked"),
            (result.elsewhere, "already in another schedule"),
        ]
        for count, words in skips:
            if count:
                messages.info(request, f"{count} {words}.")
        if result.merit_to_confirm:
            messages.warning(
                request,
                f"{result.merit_to_confirm} have merit to confirm; "
                "they are prepared at the base amount.",
            )
        return _back(self.program, schedule)


@method_decorator(
    reauthentication_required(enabled=lambda r: r.POST.get("action") in RELEASE_ACTIONS),
    name="post",
)
class BulkView(ProgramStaffRequiredMixin, View):
    """Approve or release payouts (selected, or all in the source status). Heads only; release
    asks for the password again, and allauth replays this POST after it."""

    level = ProgramMembership.Level.HEAD
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, program: str, schedule: int) -> HttpResponse:
        form = BulkForm(request.POST)
        if not form.is_valid():
            messages.warning(request, str(next(iter(form.errors.values()))[0]))
            return _back(self.program, schedule)
        action = form.cleaned_data["action"]
        release = action in RELEASE_ACTIONS
        try:
            result = services.bulk(
                actor=_actor(request),
                program=self.program,
                schedule_id=schedule,
                action="release" if release else "approve",
                ids=None if action.endswith("_all") else form.cleaned_data["ids"],
                request=request,
            )
        except ValidationError as error:
            messages.warning(request, _error_text(error))
            return _back(self.program, schedule)
        text = f"{'Released' if release else 'Approved'} {_plural(result.done)}."
        if result.skipped:
            messages.warning(request, f"{text} Skipped {len(result.skipped)}.")
        else:
            messages.success(request, text)
        for name, reason in result.skipped:
            messages.warning(request, f"{name}: {reason}" if name else reason)
        if result.remaining:
            messages.info(
                request, f"Done {result.done}. {result.remaining} more to go; click again."
            )
        return _back(self.program, schedule)


class RejectView(ProgramStaffRequiredMixin, View):
    level = ProgramMembership.Level.HEAD

    def _render(
        self, request: HttpRequest, row: Disbursement, form: RejectForm, status: int = 200
    ) -> HttpResponse:
        context = _page(
            request,
            self.program,
            "disbursements",
            row=row,
            schedule=row.schedule,
            form=form,
        )
        return render(request, "money/reject.html", context, status=status)

    def get(self, request: HttpRequest, program: str, schedule: int, pk: int) -> HttpResponse:
        found = selectors.staff_schedule(self.program, schedule)
        return self._render(request, selectors.schedule_disbursement(found, pk), RejectForm())

    def post(self, request: HttpRequest, program: str, schedule: int, pk: int) -> HttpResponse:
        found = selectors.staff_schedule(self.program, schedule)
        row = selectors.schedule_disbursement(found, pk)
        form = RejectForm(request.POST)
        if form.is_valid():
            try:
                services.reject(
                    actor=_actor(request),
                    program=self.program,
                    schedule_id=schedule,
                    disbursement_id=pk,
                    reason=form.cleaned_data["reason"],
                    request=request,
                )
            except ValidationError as error:
                form.add_error("reason", error)
            else:
                name = row.scholar_term.award.profile.full_name
                messages.success(request, f"Rejected the payout for {name}.")
                return _back(self.program, schedule)
        return self._render(request, row, form, status=400)


@method_decorator(reauthentication_required, name="post")
class RevertView(ProgramStaffRequiredMixin, View):
    level = ProgramMembership.Level.HEAD
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, program: str, schedule: int, pk: int) -> HttpResponse:
        try:
            services.revert(
                actor=_actor(request),
                program=self.program,
                schedule_id=schedule,
                disbursement_id=pk,
                request=request,
            )
        except ValidationError as error:
            messages.warning(request, _error_text(error))
        else:
            messages.success(request, "Moved back to Prepared.")
        return _back(self.program, schedule)


def _year(value: str | None) -> int:
    """A fiscal year from the query string; anything else is this year."""
    try:
        year = int(value or "")
    except ValueError:
        return timezone.localdate().year
    return year if 2000 <= year <= 2100 else timezone.localdate().year


class BudgetView(ProgramStaffRequiredMixin, View):
    def get(self, request: HttpRequest, program: str) -> HttpResponse:
        year = _year(request.GET.get("year"))
        summary = selectors.budget_summary(self.program, year)
        context = _page(
            request,
            self.program,
            "budget",
            summary=summary,
            figures=selectors.budget_figures(summary),
            schedules=selectors.year_schedules(self.program, year),
            previous_year=year - 1,
            next_year=year + 1,
            can_decide=_can_decide(self.membership),
        )
        return render(request, "money/budget.html", context)


@method_decorator(reauthentication_required, name="post")
class BudgetEditView(ProgramStaffRequiredMixin, View):
    """Heads set the year's budget; saving asks for the password again (spec §10)."""

    level = ProgramMembership.Level.HEAD

    def _render(self, request: HttpRequest, form: BudgetForm, status: int = 200) -> HttpResponse:
        context = _page(request, self.program, "budget", form=form)
        return render(request, "money/budget_form.html", context, status=status)

    def get(self, request: HttpRequest, program: str) -> HttpResponse:
        year = _year(request.GET.get("year"))
        amount = selectors.budget_summary(self.program, year).amount
        return self._render(request, BudgetForm(initial={"year": year, "amount": amount}))

    def post(self, request: HttpRequest, program: str) -> HttpResponse:
        form = BudgetForm(request.POST)
        if not form.is_valid():
            return self._render(request, form, status=400)
        year = form.cleaned_data["year"]
        try:
            services.set_budget(
                actor=_actor(request),
                program=self.program,
                year=year,
                amount=form.cleaned_data["amount"],
                request=request,
            )
        except ValidationError as error:
            form.add_error("amount", error)
            return self._render(request, form, status=400)
        messages.success(request, f"Budget for {year} saved.")
        return redirect(reverse("money:budget", args=[self.program.slug]) + f"?year={year}")
