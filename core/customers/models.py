from django.db import models

# Create your models here.
class Customer(models.Model):
    class IDType(models.TextChoices):
        GHANACARD = "GHANACARD", "GhanaCard"
        PASSPORT = "PASSPORT", "Passport"
        VOTERID = "VOTERID", "VoterID"
    
    class UserStatus(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        BLACKLISTED = "BLACKLISTED", "Blacklisted"
    
    national_id_type = models.CharField(
        max_length=50,
        choices=IDType.choices,
        default=IDType.GHANACARD
    )
    national_id_number = models.CharField(
        max_length=50,
        unique=True
    )
    date_of_birth = models.DateField()
    phone_number = models.CharField()
    email = models.EmailField()
    residential_address = models.CharField(
        max_length=50,
        help_text="Eg. AD-025-6434, Fawoade"
    )