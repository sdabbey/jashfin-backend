from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from loans.models import (
    LoanProduct, LoanApplication, Loan, LoanApproval,
    StudentVerification, BusinessVerification, EmploymentVerification,
    SustainabilityVerification
)
from customers.models import Customer
from institutions.models import Employee, FinancialInstitution

User = get_user_model()
class LoanModelsTestCase(TestCase):
    def setUp(self):
        # Sample Customer
        self.customer = Customer.objects.create(
            national_id_type="GHANACARD",
            national_id_number="GHA1234567",
            date_of_birth="1998-01-01",
            phone_number="0241234567",
            email="test@example.com",
            residential_address="Accra, Ghana",
            occupation="Student",
            monthly_income=1000
        )

        # Dummy Financial Institution
        self.fi = FinancialInstitution.objects.create(
            legal_name="JashFin Bank Ltd",
            trading_name="JashFin",
            company_registration_number="RC12345678",
            license_number="LIC-0001",
            licensing_act="Act 930",
            institution_type=FinancialInstitution.InstitutionType.BANK,
            minimum_required_capital=1000000,
            declared_paid_up_capital=1000000,
            can_accept_deposits=True,
            can_lend=True
        )

        # Dummy User for Employee
        self.user = User.objects.create_user(
            username="johndoe",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            password="password123"
        )

        # Sample Employee
        self.employee = Employee.objects.create(
            user=self.user,
            institution=self.fi,
            role=Employee.Role.CREDIT_OFFICER
        )

        # Loan Product
        self.product = LoanProduct.objects.create(
            name="Educredit",
            code="EDUCREDIT",
            description="Short-term liquidity for students",
            min_amount=Decimal("50.00"),
            max_amount=Decimal("500.00"),
            max_tenure_days=30,
            interest_rate=Decimal("5.0")
        )

        # Loan Application
        self.loan_app = LoanApplication.objects.create(
            customer=self.customer,
            product=self.product,
            requested_amount=Decimal("200.00"),
            tenure_days=30,
            status=LoanApplication.Status.DRAFT
        )

        # Loan linked to application
        self.loan = Loan.objects.create(
            application=self.loan_app,
            principal_amount=self.loan_app.requested_amount,
            interest_rate=self.product.interest_rate,
            tenure_months=1,
            status=Loan.Status.ACTIVE,
            disbursed_at=timezone.now(),
            maturity_date=timezone.now().date()
        )
    def test_loan_application_str(self):
        self.assertIn("LoanApplication", str(self.loan_app))
        self.assertIn(self.customer.national_id_number, str(self.loan_app))

    def test_loan_str(self):
        self.assertEqual(str(self.loan.principal_amount), "200.00")

    def test_loan_approval(self):
        approval = LoanApproval.objects.create(
            loan=self.loan_app,
            reviewed_by=self.employee,
            decision=LoanApproval.Decision.AUTO_APPROVED,
            justification=""
        )
        self.assertEqual(approval.decision, "AUTO_APPROVED")
        self.assertEqual(approval.reviewed_by.id, self.employee.id)
        self.assertIn(str(self.loan_app.id), str(approval))

    def test_student_verification(self):
        student_ver = StudentVerification.objects.create(
            application=self.loan_app,
            institution_name="University of Ghana",
            school_id_number="UG12345",
            student_id_image=SimpleUploadedFile("id.jpg", b"file_content")
        )
        self.assertFalse(student_ver.verified)
        student_ver.verified = True
        student_ver.verified_at = timezone.now()
        student_ver.save()
        self.assertTrue(student_ver.verified)

    def test_business_verification(self):
        biz_ver = BusinessVerification.objects.create(
            application=self.loan_app,
            business_name="Test Biz",
            registration_number="RG12345",
            years_in_operation=2,
            business_address="Accra"
        )
        self.assertFalse(biz_ver.verified)
        biz_ver.verified = True
        biz_ver.save()
        self.assertTrue(biz_ver.verified)

    def test_employment_verification(self):
        emp_ver = EmploymentVerification.objects.create(
            application=self.loan_app,
            employer_name="ABC Ltd",
            employment_type="Permanent",
            monthly_salary=Decimal("1000.00")
        )
        self.assertFalse(emp_ver.verified)
        emp_ver.verified = True
        emp_ver.save()
        self.assertTrue(emp_ver.verified)

    def test_sustainability_verification(self):
        sus_ver = SustainabilityVerification.objects.create(
            application=self.loan_app,
            enterprise_name="GreenTech",
            sustainability_focus="Clean Energy",
            impact_description="Solar panels production"
        )
        self.assertFalse(sus_ver.verified)
        sus_ver.verified = True
        sus_ver.save()
        self.assertTrue(sus_ver.verified)

