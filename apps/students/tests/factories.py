from datetime import date
from decimal import Decimal

import factory

from apps.accounts.tests.factories import UserFactory
from apps.programs.models import School
from apps.programs.tests.factories import SchoolFactory
from apps.students.models import EducationRecord, FamilyMember, StudentProfile


class ProfileFactory(factory.django.DjangoModelFactory[StudentProfile]):
    class Meta:
        model = StudentProfile

    user = factory.declarations.SubFactory(UserFactory, verified=True)
    first_name = factory.faker.Faker("first_name", locale="en_PH")
    last_name = factory.faker.Faker("last_name", locale="en_PH")


class FullProfileFactory(ProfileFactory):
    birth_date = date(2006, 3, 14)
    sex = StudentProfile.Sex.FEMALE
    phone = "+639171234567"
    address_line = "12 Mabini Street"
    barangay = "ususan"
    residing_since = 2010
    is_registered_voter = False
    monthly_household_income = Decimal("25000.00")


class FamilyMemberFactory(factory.django.DjangoModelFactory[FamilyMember]):
    class Meta:
        model = FamilyMember

    profile = factory.declarations.SubFactory(ProfileFactory)
    relation = FamilyMember.Relation.MOTHER
    name = factory.faker.Faker("name", locale="en_PH")


class EducationRecordFactory(factory.django.DjangoModelFactory[EducationRecord]):
    class Meta:
        model = EducationRecord

    profile = factory.declarations.SubFactory(ProfileFactory)
    level = EducationRecord.Level.COLLEGE
    school = factory.declarations.SubFactory(SchoolFactory, grading_scale=School.Scale.PERCENT)
    is_current = True
