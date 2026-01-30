from django.db import models
from django.core.exceptions import ValidationError
# Create your models here.
class FinancialInstitution(models.Model):
    class InstitutionType(models.TextChoices):
        BANK = "BANK", "Bank"
        SDI = "SDI", "Specialised Deposit-Taking Institution"
        MFI_TIER_2 = "MFI_TIER_2", "Microfinance Institution (Tier 2)"
        RCB = "RCB", "Rural & Community Bank"
        NBFI = "NBFI", "Non-Bank Financial Institution"
        FINTECH = "FINTECH", "Fintech / Electronic Money Issuer"

    class LicenseStatus(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        REVOKED = "REVOKED", "Revoked"
    
    # Legal Identity & Licensing
    legal_name = models.CharField(max_length=255)
    trading_name = models.CharField(max_length=255, blank=True)
    company_registration_number = models.CharField(
        max_length=100,
        help_text="Registered under the Companies Act, 2019 (Act 992)"
    )
    license_number = models.CharField(
        max_length=100,
        unique=True,
        help_text="Issued by the Bank of Ghana"
    )
    licensing_act = models.CharField(
        max_length=50,
        help_text="e.g. Act 930, Act 774, Act 987"
    )
    regulator = models.CharField(
        max_length=100,
        default="Bank of Ghana",
        editable=False
    )
    license_status = models.CharField(
        max_length=20,
        choices=LicenseStatus.choices,
        default=LicenseStatus.ACTIVE
    )
    institution_type = models.CharField(
        max_length=20,
        choices=InstitutionType.choices
    )

    # Permissible Activities
    can_accept_deposits = models.BooleanField(default=False)
    can_lend = models.BooleanField(default=True)
    can_issue_e_money = models.BooleanField(default=False)
    can_transmit_funds = models.BooleanField(default=False)
    can_manage_investments = models.BooleanField(default=False)

    # Capital Adequacy
    minimum_required_capital = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Regulatory minimum capital requirement"
    )
    declared_paid_up_capital = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Declared paid-up capital of the institution"
    )
    capital_currency = models.CharField(
        max_length=10,
        default="GHS"
    )

    # Governance & Compliance Attestations
    beneficial_ownership_disclosed = models.BooleanField(default=False)
    fit_and_proper_compliant = models.BooleanField(default=False)
    governance_framework_submitted = models.BooleanField(default=False)

    # System Control
    is_active = models.BooleanField(
        default=True,
        help_text="Only one FinancialInstitution may be active at any time"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Constraints
    def clean(self):
        if self.is_active:
            qs = FinancialInstitution.objects.filter(is_active=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    "Only one active FinancialInstitution is allowed."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.legal_name