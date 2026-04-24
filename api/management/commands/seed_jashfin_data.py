from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from customers.models import Customer
from institutions.models import Employee, FinancialInstitution
from loans.models import LoanProduct

User = get_user_model()

PRODUCTS = [
    {
        "name": "Educredit",
        "code": LoanProduct.Code.EDU,
        "description": "Educational loans for students with flexible repayment.",
        "min_amount": Decimal("50"),
        "max_amount": Decimal("500"),
        "max_tenure_days": 180,
        "interest_rate": Decimal("8.00"),
    },
    {
        "name": "Youthcredit",
        "code": LoanProduct.Code.YOUTH,
        "description": "Empowering young entrepreneurs aged 18-35.",
        "min_amount": Decimal("100"),
        "max_amount": Decimal("1500"),
        "max_tenure_days": 365,
        "interest_rate": Decimal("8.00"),
    },
    {
        "name": "Quickcredit",
        "code": LoanProduct.Code.QUICK,
        "description": "Fast emergency loans.",
        "min_amount": Decimal("50"),
        "max_amount": Decimal("800"),
        "max_tenure_days": 90,
        "interest_rate": Decimal("10.00"),
    },
    {
        "name": "Ecocredit",
        "code": LoanProduct.Code.ECO,
        "description": "Green loans for sustainable businesses.",
        "min_amount": Decimal("500"),
        "max_amount": Decimal("3000"),
        "max_tenure_days": 730,
        "interest_rate": Decimal("7.00"),
    },
]


class Command(BaseCommand):
    help = "Seed loan products, demo institution/staff, and optional demo borrower (Phase B dev)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--borrower-password",
            default="demo123",
            help="Password for demo borrower user (default: demo123)",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        for p in PRODUCTS:
            LoanProduct.objects.update_or_create(
                code=p["code"],
                defaults={
                    "name": p["name"],
                    "description": p["description"],
                    "min_amount": p["min_amount"],
                    "max_amount": p["max_amount"],
                    "max_tenure_days": p["max_tenure_days"],
                    "interest_rate": p["interest_rate"],
                    "is_active": True,
                },
            )
        self.stdout.write(self.style.SUCCESS("Loan products OK"))

        if not FinancialInstitution.objects.exists():
            fi = FinancialInstitution.objects.create(
                legal_name="JASHFIN Micro-Credit Ltd",
                trading_name="JASHFIN",
                company_registration_number="CS-000000",
                license_number="BOG-MFC-DEMO-001",
                licensing_act="Act 930",
                institution_type=FinancialInstitution.InstitutionType.MFI_TIER_2,
                minimum_required_capital=Decimal("1000000"),
                declared_paid_up_capital=Decimal("500000"),
                is_active=True,
            )
            self.stdout.write(self.style.SUCCESS(f"Created institution {fi.legal_name}"))
        else:
            fi = FinancialInstitution.objects.filter(is_active=True).first()
            if fi is None:
                fi = FinancialInstitution.objects.first()

        staff_email = "staff@jashfin.local"
        if not User.objects.filter(username=staff_email).exists():
            u = User.objects.create_user(
                username=staff_email,
                email=staff_email,
                password="staff123",
                first_name="Staff",
                last_name="User",
                type=User.UserType.EMPLOYEE,
                is_staff=True,
            )
            Employee.objects.create(
                institution=fi,
                user=u,
                role=Employee.Role.ADMIN,
                is_active=True,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Staff user {staff_email} / staff123 (token via POST /api/v1/auth/staff-token/)"
                )
            )

        borrower_email = "borrower@jashfin.local"
        bpw = options["borrower_password"]
        if not User.objects.filter(username=borrower_email).exists():
            bu = User.objects.create_user(
                username=borrower_email,
                email=borrower_email,
                password=bpw,
                first_name="Demo",
                last_name="Borrower",
                type=User.UserType.CUSTOMER,
            )
            Customer.objects.create(
                user=bu,
                national_id_type=Customer.IDType.GHANACARD,
                national_id_number="GHA-000000000-0",
                date_of_birth="1995-01-15",
                phone_number="0244000000",
                email=borrower_email,
                residential_address="Accra",
                occupation="Trader",
                monthly_income=Decimal("2000.00"),
                status=Customer.Status.ACTIVE,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Borrower {borrower_email} / {bpw} (token via POST /api/v1/auth/customer-token/)"
                )
            )
