from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db import models


class User(AbstractUser):
    # Days of silence after which an application needs a follow-up.
    follow_up_days = models.PositiveSmallIntegerField(
        default=7,
        validators=[MinValueValidator(1)],
    )
