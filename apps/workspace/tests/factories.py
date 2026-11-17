import factory

from apps.accounts.tests.factories import UserFactory
from apps.workspace.models import Notification


class NotificationFactory(factory.django.DjangoModelFactory[Notification]):
    class Meta:
        model = Notification

    recipient = factory.declarations.SubFactory(UserFactory)
    kind = "application_received"
    title = factory.declarations.Sequence(lambda n: f"Notice {n}")
    url = "/me/applications/"
