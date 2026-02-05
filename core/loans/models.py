from django.db import models
from customers.models import Customer, CustomerConsent
from institutions.models import Employee
# Create your models here.

class LoanProduct(models.Model):
    class Code(models.TextChoices):
        EDU = "EDUCREDIT", "Educredit"
        YOUTH = "YOUTHCREDIT", "Youthcredit"
        QUICK = "QUICKCREDIT", "Quickcredit"
        ECO = "ECOCREDIT", "Ecocredit"

    name = models.CharField(max_length=100, unique=True)

    code = models.CharField(
        max_length=20,
        choices=Code.choices,
        unique=True
    )

    description = models.TextField()

    min_amount = models.DecimalField(max_digits=12, decimal_places=2)
    max_amount = models.DecimalField(max_digits=12, decimal_places=2)

    max_tenure_days = models.PositiveSmallIntegerField(
        help_text="System uses days, not months"
    )

    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)


class LoanApplication(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"
    
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="loan_applications"
    )
    product = models.ForeignKey(
        LoanProduct,
        on_delete=models.PROTECT
    )
    requested_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    ) 
    tenure_days = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    # def __str__(self):
        # return f"LoanApplication #{self.id} - {self.customer_id} - {self.product.code}"
       
    def __str__(self):
        return f"LoanApplication #{self.id} - {self.customer.national_id_number} - {self.product.code}"




class Loan(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        DEFAULTED = "DEFAULTED", "Defaulted"
        WRITTEN_OFF = "WRITTEN_OFF", "Written Off"

    application = models.OneToOneField(
        LoanApplication,
        on_delete=models.PROTECT,
        related_name="loan"
    )

    principal_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Annual percentage rate"
    )

    tenure_months = models.PositiveSmallIntegerField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )

    disbursed_at = models.DateTimeField()
    maturity_date = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)

class LoanApproval(models.Model):
    class Decision(models.TextChoices):
        AUTO_APPROVED = "AUTO_APPROVED", "Auto Approved"
        MANUAL_APPROVED = "MANUAL_APPROVED", "Manual Approved"
        REJECTED = "REJECTED", "Rejected"

    loan = models.OneToOneField(
        "LoanApplication",
        on_delete=models.CASCADE,
        related_name="approval"
    )
    reviewed_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Employee who manually reviewed the loan (if applicable)"
    )
    decision = models.CharField(max_length=20, choices=Decision.choices)
    justification = models.TextField(blank=True, help_text="Reason for manual decision or override")
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Loan {self.loan.id} - {self.decision}"


class StudentVerification(models.Model):
    application = models.OneToOneField(
        LoanApplication,
        on_delete=models.CASCADE,
        related_name="student_verification"
    )

    institution_name = models.CharField(max_length=255)

    school_id_number = models.CharField(max_length=100)

    expected_graduation_date = models.DateField(
        null=True,
        blank=True,
        help_text="Null if already graduated"
    )

    student_id_image = models.ImageField(
        upload_to="student_ids/"
    )

    verified = models.BooleanField(default=False)

    verified_at = models.DateTimeField(null=True, blank=True)


class BusinessVerification(models.Model):
    application = models.OneToOneField(
        LoanApplication,
        on_delete=models.CASCADE,
        related_name="business_verification"
    )

    business_name = models.CharField(max_length=255)

    registration_number = models.CharField(
        max_length=100,
        help_text="Registrar General / informal ID if unregistered"
    )

    tin_number = models.CharField(
        max_length=50,
        null=True,
        blank=True
    )

    years_in_operation = models.PositiveSmallIntegerField()

    business_address = models.CharField(max_length=255)

    verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)


class EmploymentVerification(models.Model):
    application = models.OneToOneField(
        LoanApplication,
        on_delete=models.CASCADE,
        related_name="employment_verification"
    )

    employer_name = models.CharField(max_length=255)

    employment_type = models.CharField(
        max_length=50,
        help_text="Permanent, Contract, Casual"
    )

    monthly_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    payslip_document = models.FileField(
        upload_to="payslips/",
        null=True,
        blank=True
    )

    verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

class SustainabilityVerification(models.Model):
    application = models.OneToOneField(
        LoanApplication,
        on_delete=models.CASCADE,
        related_name="sustainability_verification"
    )
    enterprise_name = models.CharField(max_length=255)
    sustainability_focus = models.CharField(
        max_length=255,
        help_text="e.g. recycling, clean energy, agribusiness"
    )

    impact_description = models.TextField()

    verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
