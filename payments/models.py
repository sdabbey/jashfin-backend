from django.conf import settings
from django.db import models

from loans.models import Loan


class LoanPayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    class Method(models.TextChoices):
        MOMO = "MOMO", "Mobile Money"
        CASH = "CASH", "Cash"
        BANK = "BANK", "Bank transfer"

    loan = models.ForeignKey(
        Loan,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_at = models.DateTimeField()
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.MOMO)
    reference = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.COMPLETED,
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_payments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_at", "-id"]

    def __str__(self):
        return f"Payment {self.amount} on loan {self.loan_id}"
