import uuid
from django.db import models
from django.core.exceptions import ValidationError
from loans.models import Loan
from django.db.models import Sum, Case, When, DecimalField

class LedgerAccount(models.Model):
    class AccountTypes(models.TextChoices):
        ASSET = "ASSET", "Asset"
        EQUITY = "EQUITY", "Equity"
        LIABILITY = "LIABILITY", "Liability"
        EXPENSE = "EXPENSE", "Expense"
        REVENUE = "REVENUE", "Revenue"
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    account_type = models.CharField(max_length=20, choices=AccountTypes.choices)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    
    

    def get_balance(self):
        totals = self.entries.aggregate(
            balance=Sum(
                Case(
                    When(entry_type="DEBIT", then="amount"),
                    When(entry_type="CREDIT", then=-1 * models.F("amount")),
                    output_field=DecimalField(),
                )
            )
        )
        return totals["balance"] or 0

    

class LedgerEntry(models.Model):
    class EntryTypes(models.TextChoices):
        DEBIT = "DEBIT", "Debit"
        CREDIT = "CREDIT", "Credit"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ledger_account = models.ForeignKey(
        LedgerAccount,
        on_delete=models.PROTECT,
        related_name="entries"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    entry_type = models.CharField(max_length=6, choices=EntryTypes.choices)
    reference = models.CharField(max_length=255)
    loan = models.ForeignKey(
        Loan,
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )

    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        # Allow inserts, block updates
        if self.pk and not kwargs.get("force_insert", False):
            raise ValidationError("Ledger entries are immutable.")
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        raise ValidationError("Ledger entries cannot be deleted")
    
