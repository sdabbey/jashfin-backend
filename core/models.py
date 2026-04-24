# core/models.py (or users/models.py)
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class UserType(models.TextChoices):
        EMPLOYEE = "EMPLOYEE", "Employee"
        CUSTOMER = "CUSTOMER", "Customer"

    type = models.CharField(
        max_length=20,
        choices=UserType.choices,
        default=UserType.CUSTOMER,
        help_text="Distinguish between employee and customer users"
    )

    def is_employee(self):
        return self.type == self.UserType.EMPLOYEE

    def is_customer(self):
        return self.type == self.UserType.CUSTOMER

    def __str__(self):
        return f"{self.username} ({self.type})"
