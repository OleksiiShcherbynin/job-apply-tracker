import pytest
from django.core.exceptions import ValidationError

from accounts.factories import UserFactory


@pytest.mark.django_db
def test_create_user_default_follow_up_days():
    user = UserFactory()
    assert user.follow_up_days == 7


@pytest.mark.django_db  # full_clean проверяет уникальность username запросом в БД
def test_follow_up_days_min_1():
    user = UserFactory.build(follow_up_days=0)  # build: в память, без сохранения
    with pytest.raises(ValidationError):
        user.full_clean()
