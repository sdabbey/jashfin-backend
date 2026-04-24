"""Create a Django superuser with User.type=EMPLOYEE for the staff /admin portal."""

import getpass

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from core.models import User


class Command(BaseCommand):
    help = (
        "Create a superuser marked as EMPLOYEE (staff portal + Django admin). "
        "Prompts for password. Example: python manage.py create_staff_superuser admin admin@company.com"
    )

    def add_arguments(self, parser):
        parser.add_argument("username", type=str)
        parser.add_argument("email", type=str)

    def handle(self, *args, **options):
        username = options["username"].strip()
        email = options["email"].strip()
        if not username or not email:
            raise CommandError("username and email are required.")

        if User.objects.filter(username=username).exists():
            raise CommandError(f"User {username!r} already exists.")

        password = getpass.getpass("Password: ")
        password2 = getpass.getpass("Password (again): ")
        if password != password2:
            raise CommandError("Passwords do not match.")
        if not password:
            raise CommandError("Password cannot be empty.")

        try:
            User.objects.create_superuser(
                username=username,
                email=email,
                password=password,
                type=User.UserType.EMPLOYEE,
            )
        except IntegrityError as e:
            raise CommandError(str(e)) from e

        self.stdout.write(self.style.SUCCESS(f"Superuser {username!r} created (type=EMPLOYEE)."))
