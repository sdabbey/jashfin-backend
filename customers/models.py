import uuid
from django.db import models
from django.conf import settings

# Create your models here.
class Customer(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_profile"
    )
    class IDType(models.TextChoices):
        GHANACARD = "GHANACARD", "GhanaCard"
        PASSPORT = "PASSPORT", "Passport"
        VOTERID = "VOTERID", "VoterID"
    
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        BLACKLISTED = "BLACKLISTED", "Blacklisted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)    
    national_id_type = models.CharField(
        max_length=20,
        choices=IDType.choices,
        default=IDType.GHANACARD
    )
    national_id_number = models.CharField(
        max_length=50,
        unique=True
    )
    date_of_birth = models.DateField()
    phone_number = models.CharField(max_length=20)
    email = models.EmailField(null=True, blank=True)
    residential_address = models.CharField(
        max_length=255,
        help_text="Eg. AD-025-6434, Fawoade"
    )
    occupation = models.CharField(max_length=100)
    monthly_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Approximate monthly income (GHS)"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.national_id_type} - {self.national_id_number}"

class CustomerConsent(models.Model):
    class ConsentType(models.TextChoices):
        TERMS_AND_CONDITIONS = "TERMS_AND_CONDITIONS", "Terms and Conditions"
        DATA_PROCESSING = "DATA_PROCESSING", "Data Processing"
        CREDIT_BUREAU = "CREDIT_BUREAU", "Credit Bureau"
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="consents"
    )
    consent_type  = models.CharField(
        max_length=50,
        choices=ConsentType.choices
    )
    version = models.CharField(max_length=50)
    granted_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("customer", "consent_type", "version")
    
    def __str__(self):
        return f"{self.customer_id} - {self.consent_type} ({self.version})"