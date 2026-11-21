import factory

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs.tests.factories import ProgramFactory
from apps.workspace.models import (
    Notification,
    ReplyTemplate,
    SupportReply,
    SupportRequest,
    Task,
)


class NotificationFactory(factory.django.DjangoModelFactory[Notification]):
    class Meta:
        model = Notification

    recipient = factory.declarations.SubFactory(UserFactory)
    kind = "application_received"
    title = factory.declarations.Sequence(lambda n: f"Notice {n}")
    url = "/me/applications/"


class TaskFactory(factory.django.DjangoModelFactory[Task]):
    class Meta:
        model = Task

    owner = factory.declarations.SubFactory(UserFactory, role=User.Role.STAFF)
    program = factory.declarations.SubFactory(ProgramFactory)
    title = factory.declarations.Sequence(lambda n: f"Task {n}")


class SupportRequestFactory(factory.django.DjangoModelFactory[SupportRequest]):
    class Meta:
        model = SupportRequest

    sender = factory.declarations.SubFactory(UserFactory)
    topic = "other"
    message = factory.declarations.Sequence(lambda n: f"Question {n}")


class ReplyTemplateFactory(factory.django.DjangoModelFactory[ReplyTemplate]):
    class Meta:
        model = ReplyTemplate

    title = factory.declarations.Sequence(lambda n: f"Template {n}")
    body = "Hi {first_name}."
    created_by = factory.declarations.SubFactory(UserFactory, role=User.Role.SUPER_ADMIN)
    updated_by = factory.declarations.SelfAttribute("created_by")


class SupportReplyFactory(factory.django.DjangoModelFactory[SupportReply]):
    class Meta:
        model = SupportReply

    request = factory.declarations.SubFactory(SupportRequestFactory)
    author = factory.declarations.SubFactory(UserFactory, role=User.Role.SUPER_ADMIN)
    channel = "app"
    body = factory.declarations.Sequence(lambda n: f"Answer {n}")
