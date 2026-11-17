import factory

from apps.accounts.tests.factories import UserFactory
from apps.workspace.models import Notification


class NotificationFactory(factory.django.DjangoModelFactory[Notification]):
    class Meta:
        model = Notification

    recipient = factory.SubFactory(UserFactory)
    kind = "application_received"
    title = factory.Sequence(lambda n: f"Notice {n}")
    url = "/me/applications/"
