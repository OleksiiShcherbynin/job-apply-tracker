from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class User(AbstractUser):
    # Days of silence after which an application needs a follow-up.
    follow_up_days = models.PositiveSmallIntegerField(
        default=7,
        validators=[MinValueValidator(1)],
    )
    # Inbox shows vacancies scored at least this much (unscored manual ones always).
    inbox_min_score = models.PositiveSmallIntegerField(
        default=40,
        validators=[MaxValueValidator(100)],
    )
    # After this many days an untouched vacancy leaves the default inbox.
    inbox_fresh_days = models.PositiveSmallIntegerField(
        default=5,
        validators=[MinValueValidator(1)],
    )
