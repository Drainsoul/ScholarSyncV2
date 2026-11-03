from typing import Any

import factory
from allauth.account.models import EmailAddress

from apps.accounts.models import User

DEFAULT_PASSWORD = "factory-pass-2026"


class UserFactory(factory.django.DjangoModelFactory[User]):
    class Meta:
        model = User
        skip_postgeneration_save = True

    full_name = factory.faker.Faker("name", locale="en_PH")
    email = factory.declarations.Sequence(lambda n: f"user{n}@scholarsync.test")
    role = User.Role.STUDENT

    @classmethod
    def _create(cls, model_class: type[User], *args: Any, **kwargs: Any) -> User:
        password = kwargs.pop("password", DEFAULT_PASSWORD)
        return model_class.objects.create_user(password=password, **kwargs)

    @factory.declarations.PostGeneration
    def verified(self, create: bool, extracted: bool | None, **kwargs: Any) -> None:
        if not create:
            return
        EmailAddress.objects.create(
            user=self,
            email=self.email,
            verified=True if extracted is None else extracted,
            primary=True,
        )
