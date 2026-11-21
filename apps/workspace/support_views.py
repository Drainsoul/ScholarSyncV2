"""Support screens: the student's form, and the inboxes where the office and program staff answer.

The office and program views are shared; a scope mixin says whose requests they show (every
request, or one program's), which layout they render in and how they link (as in task_views.py).
"""

from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.views import View

from apps.accounts.models import User
from apps.core.htmx import HtmxHttpRequest, close_dialog
from apps.core.permissions import (
    ProgramStaffRequiredMixin,
    StudentRequiredMixin,
    SuperAdminRequiredMixin,
)
from apps.core.shell import shell_context
from apps.programs.models import Program

from . import reply_templates, support
from .forms import EmailReplyForm, ReplyForm, ReplyTemplateForm, SupportForm
from .models import ReplyTemplate, SupportRequest

PAGE_SIZE = 25
FORMS = ("reply", "email")


def _user(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)
    return user


QUESTION_PREVIEW = 200


def _student_tabs(request: HttpRequest) -> list[dict[str, Any]]:
    """Contact the office and Replies, with the student's unread replies on the second."""
    contact, replies = reverse("support:student"), reverse("support:replies")
    return [
        {
            "label": "Contact the office",
            "url": contact,
            "current": request.path == contact,
            "count": 0,
        },
        {
            "label": "Replies",
            "url": replies,
            "current": request.path == replies,
            "count": support.unread_replies(_user(request)),
        },
    ]


class StudentRepliesView(StudentRequiredMixin, View):
    """Every answer the student has had, newest first; opening the page marks them read."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest) -> HttpResponse:
        user = _user(request)
        page = Paginator(support.student_replies(user), PAGE_SIZE).get_page(request.GET.get("page"))
        items = []
        for reply in page.object_list:
            question = reply.request.message
            if len(question) > QUESTION_PREVIEW:
                question = question[:QUESTION_PREVIEW] + "\u2026"
            items.append(
                {
                    "reply": reply,
                    "question": question,
                    "sender": support.signer(reply.request, reply.author),
                    "new": reply.read_at is None,
                }
            )
        if request.method == "GET":
            # Only the replies on this page have been seen; the counts below already drop them.
            seen = [reply.pk for reply in page.object_list if reply.read_at is None]
            support.mark_replies_read(user, timezone.now(), pks=seen)
        context = {
            **shell_context(request, area="student"),
            "page": page,
            "items": items,
            "tabs": _student_tabs(request),
        }
        return render(request, "workspace/support/replies.html", context)


class StudentSupportView(StudentRequiredMixin, View):
    template_name = "workspace/support/student.html"

    def _render(self, request: HttpRequest, form: SupportForm) -> HttpResponse:
        context = {
            **shell_context(request, area="student"),
            "form": form,
            "rows": support.own_rows(_user(request)),
            "tabs": _student_tabs(request),
            "replies_url": reverse("support:replies"),
        }
        return render(request, self.template_name, context)

    def get(self, request: HttpRequest) -> HttpResponse:
        return self._render(request, SupportForm())

    def post(self, request: HttpRequest) -> HttpResponse:
        form = SupportForm(request.POST)
        if not form.is_valid():
            return self._render(request, form)
        try:
            support.send(
                sender=_user(request), now=timezone.now(), request=request, **form.cleaned_data
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self._render(request, form)
        messages.success(request, support.SEND_SUCCESS)
        return redirect("support:student")


class SupportScope:
    """Whose requests a view shows, where it renders and how it links (one subclass per area)."""

    layout = ""

    @property
    def scope_program(self) -> Program | None:
        raise NotImplementedError

    def support_url(self, name: str, **kwargs: Any) -> str:
        raise NotImplementedError

    def shell(self, request: HttpRequest) -> dict[str, Any]:
        raise NotImplementedError


class StaffSupportScope(ProgramStaffRequiredMixin, SupportScope):
    """The requests about the program in the URL."""

    program: Program
    layout = "layouts/staff.html"
    NAMES = {
        "inbox": "support",
        "detail": "support-detail",
        "reply": "support-reply",
        "email": "support-email",
        "answer": "support-answer",
    }

    @property
    def scope_program(self) -> Program | None:
        return self.program

    def support_url(self, name: str, **kwargs: Any) -> str:
        return reverse(
            f"workspace:{self.NAMES[name]}", kwargs={"program": self.program.slug, **kwargs}
        )

    def shell(self, request: HttpRequest) -> dict[str, Any]:
        return shell_context(request, area="staff", program=self.program)


class OfficeSupportScope(SuperAdminRequiredMixin, SupportScope):
    """Every request: the office answers them all."""

    layout = "layouts/office.html"
    NAMES = {
        "inbox": "office",
        "detail": "office-detail",
        "reply": "office-reply",
        "email": "office-email",
        "answer": "answer",
    }

    @property
    def scope_program(self) -> Program | None:
        return None

    def support_url(self, name: str, **kwargs: Any) -> str:
        return reverse(f"support:{self.NAMES[name]}", kwargs=kwargs)

    def shell(self, request: HttpRequest) -> dict[str, Any]:
        return shell_context(request, area="office")


class _Inbox(SupportScope, View):
    template_name = "workspace/support/inbox.html"
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        tab = request.GET.get("tab", "open")
        if tab not in support.OFFICE_TABS:
            tab = "open"
        scope = self.scope_program
        page = Paginator(support.inbox_rows(scope, tab), PAGE_SIZE).get_page(
            request.GET.get("page")
        )
        base = self.support_url("inbox")
        open_count = support.open_count(scope)
        context = {
            **self.shell(request),
            "layout": self.layout,
            "page": page,
            "cards": [
                {
                    "row": row,
                    "detail": self.support_url("detail", pk=row.pk),
                    "answer": self.support_url("answer", pk=row.pk),
                }
                for row in page.object_list
            ],
            "tab": tab,
            "tabs": [
                {
                    "label": label,
                    "url": base if key == "open" else f"{base}?tab={key}",
                    "current": key == tab,
                    "count": open_count if key == "open" else 0,
                }
                for key, label in support.OFFICE_TABS.items()
            ],
            "office": scope is None,
        }
        return render(request, self.template_name, context)


def _template_options(row: SupportRequest) -> list[dict[str, Any]]:
    options = []
    for template in reply_templates.picker(row):
        subject, body = reply_templates.fill(template, row)
        options.append(
            {"pk": template.pk, "title": template.title, "subject": subject, "body": body}
        )
    return options


class _Detail(SupportScope, View):
    """The request, its replies and the two reply forms; one form alone in the app dialog."""

    template_name = "workspace/support/detail.html"
    dialog_template = "workspace/support/detail_dialog.html"

    def _forms(
        self, request: HttpRequest, row: SupportRequest
    ) -> tuple[str, ReplyForm, EmailReplyForm]:
        """Unbound forms, the one in ?form= filled from ?template= or ?from= (no-JS picker)."""
        which = request.GET.get("form", "reply")
        which = which if which in FORMS else "reply"
        filled: dict[str, Any] = {}
        template = _picked(row, request.GET.get("template"))
        if template is not None:
            subject, body = reply_templates.fill(template, row)
            filled = {"subject": subject, "body": body, "template": template.pk}
        elif request.GET.get("from", "").isdigit():
            earlier = row.replies.filter(pk=int(request.GET["from"])).first()
            if earlier is not None:
                filled = {"subject": earlier.subject, "body": earlier.body}
        reply_initial = {k: v for k, v in filled.items() if k != "subject"}
        reply_form = ReplyForm(initial=reply_initial if which == "reply" else {})
        email_initial = filled if which == "email" else {}
        email_form = EmailReplyForm(
            initial={"subject": reply_templates.default_subject(row), **email_initial}
        )
        return which, reply_form, email_form

    def render_page(
        self,
        request: HtmxHttpRequest,
        row: SupportRequest,
        which: str,
        reply_form: ReplyForm,
        email_form: EmailReplyForm,
        status: int = 200,
    ) -> HttpResponse:
        dialog = bool(request.htmx)
        detail = self.support_url("detail", pk=row.pk)
        context = {
            **self.shell(request),
            "layout": self.layout,
            "row": row,
            "replies": row.replies.select_related("author", "email"),
            "options": _template_options(row),
            "which": which,
            "reply_form": reply_form,
            "email_form": email_form,
            # A refused email (the account closed meanwhile) still shows its form, with the reason.
            "can_email": row.sender.is_active or bool(email_form.is_bound and email_form.errors),
            "detail_url": detail,
            "inbox_url": self.support_url("inbox"),
            "reply_url": self.support_url("reply", pk=row.pk),
            "email_url": self.support_url("email", pk=row.pk),
            "answer_url": self.support_url("answer", pk=row.pk),
            "dialog": dialog,
        }
        name = self.dialog_template if dialog else self.template_name
        response = render(request, name, context, status=status)
        patch_vary_headers(response, ("HX-Request",))
        return response

    def get(self, request: HtmxHttpRequest, pk: int, **kwargs: Any) -> HttpResponse:
        row = support.scoped_request(self.scope_program, pk)
        which, reply_form, email_form = self._forms(request, row)
        return self.render_page(request, row, which, reply_form, email_form)


def _picked(row: SupportRequest, value: object) -> ReplyTemplate | None:
    """A template id from the form, if it is one the picker offers for this request."""
    if not str(value or "").isdigit():
        return None
    wanted = int(str(value))
    return next((t for t in reply_templates.picker(row) if t.pk == wanted), None)


class _Send(_Detail):
    """POST a reply (in the app or by email); errors show the form again."""

    http_method_names = ["post"]
    which = "reply"

    def send(self, request: HttpRequest, row: SupportRequest, form: ReplyForm) -> str:
        raise NotImplementedError

    def post(self, request: HtmxHttpRequest, pk: int, **kwargs: Any) -> HttpResponse:
        row = support.scoped_request(self.scope_program, pk)
        bound: ReplyForm = (EmailReplyForm if self.which == "email" else ReplyForm)(request.POST)
        if bound.is_valid():
            try:
                message = self.send(request, row, bound)
            except ValidationError as error:
                bound.add_error(None, error)
            else:
                messages.success(request, message)
                if request.htmx:
                    response = close_dialog(HttpResponse(status=204))
                    response["HX-Refresh"] = "true"
                    return response
                return redirect(self.support_url("detail", pk=row.pk))
        _, reply_form, email_form = self._forms(request, row)
        if self.which == "email":
            assert isinstance(bound, EmailReplyForm)
            email_form = bound
        else:
            reply_form = bound
        return self.render_page(request, row, self.which, reply_form, email_form)


class _Reply(_Send):
    which = "reply"

    def send(self, request: HttpRequest, row: SupportRequest, form: ReplyForm) -> str:
        support.reply(
            actor=_user(request),
            request_row=row,
            body=form.cleaned_data["body"],
            template=_picked(row, form.cleaned_data.get("template")),
            now=timezone.now(),
            request=request,
        )
        return "Reply sent."


class _Email(_Send):
    which = "email"

    def send(self, request: HttpRequest, row: SupportRequest, form: ReplyForm) -> str:
        support.email_reply(
            actor=_user(request),
            request_row=row,
            subject=form.cleaned_data["subject"],
            body=form.cleaned_data["body"],
            template=_picked(row, form.cleaned_data.get("template")),
            now=timezone.now(),
            request=request,
        )
        return f"Email queued to {row.sender.email}."


class _Answer(SupportScope, View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest, pk: int, **kwargs: Any) -> HttpResponse:
        row = support.scoped_request(self.scope_program, pk)
        support.answer(actor=_user(request), request_row=row, now=timezone.now(), request=request)
        messages.success(request, "Marked as answered.")
        return redirect(self.support_url("inbox"))


class OfficeSupportView(OfficeSupportScope, _Inbox):
    pass


class OfficeDetailView(OfficeSupportScope, _Detail):
    pass


class OfficeReplyView(OfficeSupportScope, _Reply):
    pass


class OfficeEmailView(OfficeSupportScope, _Email):
    pass


class AnswerView(OfficeSupportScope, _Answer):
    pass


class StaffSupportView(StaffSupportScope, _Inbox):
    pass


class StaffDetailView(StaffSupportScope, _Detail):
    pass


class StaffReplyView(StaffSupportScope, _Reply):
    pass


class StaffEmailView(StaffSupportScope, _Email):
    pass


class StaffAnswerView(StaffSupportScope, _Answer):
    pass


class TemplateListView(SuperAdminRequiredMixin, View):
    """The office's reply templates: active first, then by title."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest) -> HttpResponse:
        rows = ReplyTemplate.objects.select_related("program").order_by("-is_active", "title", "pk")
        page = Paginator(rows, PAGE_SIZE).get_page(request.GET.get("page"))
        context = {**shell_context(request, area="office"), "page": page}
        return render(request, "workspace/support/templates_list.html", context)


class _TemplateFormView(SuperAdminRequiredMixin, View):
    def _render(
        self, request: HttpRequest, form: ReplyTemplateForm, template: ReplyTemplate | None
    ) -> HttpResponse:
        context = {**shell_context(request, area="office"), "form": form, "template": template}
        return render(request, "workspace/support/template_form.html", context)

    def _save(self, request: HttpRequest, template: ReplyTemplate | None) -> HttpResponse:
        form = ReplyTemplateForm(request.POST, template=template)
        if not form.is_valid():
            return self._render(request, form, template)
        try:
            if template is None:
                reply_templates.create_template(
                    actor=_user(request), request=request, **form.cleaned_data
                )
            else:
                reply_templates.update_template(
                    actor=_user(request), template=template, request=request, **form.cleaned_data
                )
        except ValidationError as error:
            form.add_error("title", error)
            return self._render(request, form, template)
        messages.success(request, "Template saved." if template else "Template added.")
        return redirect("support:templates")


class TemplateNewView(_TemplateFormView):
    def get(self, request: HttpRequest) -> HttpResponse:
        return self._render(request, ReplyTemplateForm(), None)

    def post(self, request: HttpRequest) -> HttpResponse:
        return self._save(request, None)


class TemplateEditView(_TemplateFormView):
    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        template = get_object_or_404(ReplyTemplate, pk=pk)
        form = ReplyTemplateForm(initial=ReplyTemplateForm.initial_for(template), template=template)
        return self._render(request, form, template)

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        return self._save(request, get_object_or_404(ReplyTemplate, pk=pk))


class TemplateActiveView(SuperAdminRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        template = get_object_or_404(ReplyTemplate, pk=pk)
        active = request.POST.get("active") == "1"
        try:
            reply_templates.set_active(
                actor=_user(request), template=template, active=active, request=request
            )
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, "Template turned on." if active else "Template turned off.")
        return redirect("support:templates")
