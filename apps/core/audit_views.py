"""The audit log: every event for the office, one program's events for its head (spec §12, M11c).

Viewing the log is not audited. `ip_hash` is never shown."""

from typing import Any, ClassVar
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.programs.models import Program, ProgramMembership

from .activity import AUDIT_GROUPS, VERBS, actor_name
from .audit_selectors import AuditFilters, audit_events, details, parse_audit_filters
from .models import AuditEvent
from .permissions import ProgramStaffRequiredMixin, SuperAdminRequiredMixin
from .shell import shell_context

PAGE_SIZE = 50


def what(event: AuditEvent) -> str:
    """ "Approved a payout": the verb on its own (the Who column names the actor)."""
    verb = VERBS.get(event.action)
    return verb[0].upper() + verb[1:] if verb else event.action


def _who_query(filters: AuditFilters, who: int | None) -> str:
    params = {
        "group": filters.group,
        "start": filters.start.isoformat() if filters.start else "",
        "end": filters.end.isoformat() if filters.end else "",
        "program": filters.program,
        "who": str(who) if who is not None else "",
    }
    return "?" + urlencode({key: value for key, value in params.items() if value})


class _AuditLog(TemplateView):
    template_name = "core/audit.html"
    area: ClassVar[str]

    def scope(self) -> Program | None:
        return None

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        office = self.area == "office"
        filters = parse_audit_filters(self.request.GET, office=office)
        program = self.scope()
        page = Paginator(audit_events(filters, program=program), PAGE_SIZE).get_page(
            self.request.GET.get("page")
        )
        rows = []
        for event in page.object_list:
            actor = event.actor
            named = actor is not None and actor.role != User.Role.STUDENT
            rows.append(
                {
                    "event": event,
                    "who": actor_name(actor),
                    "who_url": _who_query(filters, actor.pk) if named and actor else "",
                    "what": what(event),
                    "record": f"{event.target_type} #{event.target_id}" if event.target_id else "",
                    "details": details(event),
                }
            )
        who_name = ""
        if filters.who is not None:
            person = User.objects.filter(pk=filters.who).first()
            who_name = actor_name(person) if person is not None else "this person"
        shell = shell_context(self.request, area=self.area, program=program if not office else None)
        return {
            **super().get_context_data(**kwargs),
            **shell,
            "layout": "layouts/office.html" if office else "layouts/staff.html",
            "office": office,
            "filters": filters,
            "groups": [(key, label) for key, (label, _prefixes) in AUDIT_GROUPS.items()],
            "programs": list(Program.objects.order_by("name")) if office else [],
            "page": page,
            "rows": rows,
            "who_name": who_name,
            "everyone_url": _who_query(filters, None),
        }


class OfficeAuditView(SuperAdminRequiredMixin, _AuditLog):
    area = "office"
    http_method_names = ["get", "head", "options"]


class ProgramAuditView(ProgramStaffRequiredMixin, _AuditLog):
    area = "staff"
    level = ProgramMembership.Level.HEAD
    http_method_names = ["get", "head", "options"]

    def scope(self) -> Program | None:
        return self.program
