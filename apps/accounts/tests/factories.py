from typing import Any

import factory

from apps.accounts.models import User

DEFAULT_PASSWORD = "factory-pass-2026"


class UserFactory(factory.django.DjangoModelFactory[User]):
    class Meta:
        model = User

    full_name = factory.faker.Faker("name", locale="en_PH")
    email = factory.declarations.Sequence(lambda n: f"user{n}@scholarsync.test")
    role = User.Role.STUDENT

    @classmethod
    def _create(cls, model_class: type[User], *args: Any, **kwargs: Any) -> User:
        password = kwargs.pop("password", DEFAULT_PASSWORD)
        return model_class.objects.create_user(password=password, **kwargs)
