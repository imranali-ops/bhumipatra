from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    CITIZEN = "citizen", "নাগরিক"
    SURVEYOR = "surveyor", "সার্ভেয়ার"
    AC_LAND = "ac_land", "সহকারী কমিশনার (ভূমি)"
    LAWYER = "lawyer", "আইনজীবী / ক্রেতা"
    ADMIN = "admin", "অ্যাডমিন"


class User(AbstractUser):
    """Custom user from day one (changing later is painful).
    New accounts get the lowest privilege; permissions are added on Day 3."""
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CITIZEN)
