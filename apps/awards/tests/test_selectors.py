import pytest

from apps.awards.models import Award
from apps.awards.selectors import holds_active_award, other_active_awards
from apps.awards.tests.factories import AwardFactory
from apps.programs.tests.factories import ProgramFactory

pytestmark = pytest.mark.django_db


def test_holds_active_award() -> None:
    award = AwardFactory.create()
    assert holds_active_award(award.profile, award.program)
    assert not holds_active_award(award.profile, ProgramFactory.create())
    Award.objects.filter(pk=award.pk).update(status=Award.Status.INACTIVE)
    assert not holds_active_award(award.profile, award.program)


def test_other_active_awards_excludes_this_program_and_inactive() -> None:
    here = AwardFactory.create()
    other = AwardFactory.create(
        source_application__profile=here.profile,
        source_application__program=ProgramFactory.create(),
    )
    AwardFactory.create(
        source_application__profile=here.profile,
        source_application__program=ProgramFactory.create(),
        status=Award.Status.INACTIVE,
    )
    assert other_active_awards(here.profile, here.program) == [other]
