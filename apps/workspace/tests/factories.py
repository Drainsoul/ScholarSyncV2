import factory

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.programs.tests.factories import ProgramFactory
from apps.workspace.models import Notification, Task


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
