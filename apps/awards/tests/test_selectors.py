import pytest

from apps.awards.models import Award
from apps.awards.selectors import holds_award, other_active_awards
from apps.awards.tests.factories import AwardFactory
from apps.programs.tests.factories import ProgramFactory

pytestmark = pytest.mark.django_db


def test_holds_award_counts_suspended_not_inactive() -> None:
    award = AwardFactory.create()
    assert holds_award(award.profile, award.program)
    assert not holds_award(award.profile, ProgramFactory.create())
    Award.objects.filter(pk=award.pk).update(status=Award.Status.SUSPENDED)
    assert holds_award(award.profile, award.program)
    for status in (Award.Status.INACTIVE, Award.Status.GRADUATED):
        Award.objects.filter(pk=award.pk).update(status=status)
        assert not holds_award(award.profile, award.program)


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
