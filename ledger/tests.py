from decimal import Decimal
from django.test import TestCase
from django.utils import timezone

from loans.models import (
    LoanProduct, LoanApplication, Loan
   
)
from ledger.models import LedgerAccount, LedgerEntry
from customers.models import Customer





class LedgerTestCase(TestCase):
    def setUp(self):
        # Ledger Accounts
        self.cash_account = LedgerAccount.objects.create(
            name="Cash/Bank",
            account_type=LedgerAccount.AccountTypes.ASSET
        )
        self.loan_receivable = LedgerAccount.objects.create(
            name="Loan Receivable",
            account_type=LedgerAccount.AccountTypes.ASSET
        )

        # Sample Loan
        self.loan_app = LoanApplication.objects.create(
            customer=Customer.objects.create(
                national_id_type="GHANACARD",
                national_id_number="GHA9876543",
                date_of_birth="1999-01-01",
                phone_number="0247654321",
                email="test2@example.com",
                residential_address="Accra",
                occupation="Student",
                monthly_income=500
            ),
            product=LoanProduct.objects.create(
                name="Quickcredit",
                code="QUICKCREDIT",
                description="Emergency liquidity",
                min_amount=Decimal("50.00"),
                max_amount=Decimal("200.00"),
                max_tenure_days=30,
                interest_rate=Decimal("10.0")
            ),
            requested_amount=Decimal("100.00"),
            tenure_days=30
        )

        self.loan = Loan.objects.create(
            application=self.loan_app,
            principal_amount=self.loan_app.requested_amount,
            interest_rate=Decimal("10.0"),
            tenure_months=1,
            status=Loan.Status.ACTIVE,
            disbursed_at=timezone.now(),
            maturity_date=timezone.now().date()
        )

    def test_disbursement_entry(self):
        LedgerEntry.objects.create(
            ledger_account=self.loan_receivable,
            amount=self.loan.principal_amount,
            entry_type=LedgerEntry.EntryTypes.DEBIT,
            reference=f"Disbursement Loan #{self.loan.id}",
            loan=self.loan
        )
        LedgerEntry.objects.create(
            ledger_account=self.cash_account,
            amount=self.loan.principal_amount,
            entry_type=LedgerEntry.EntryTypes.CREDIT,
            reference=f"Disbursement Loan #{self.loan.id}",
            loan=self.loan
        )

        self.assertEqual(self.loan_receivable.get_balance(), Decimal("100.00"))
        self.assertEqual(self.cash_account.get_balance(), Decimal("-100.00"))

    def test_repayment_entry(self):
        repayment_amount = Decimal("50.00")
        LedgerEntry.objects.create(
            ledger_account=self.cash_account,
            amount=repayment_amount,
            entry_type=LedgerEntry.EntryTypes.DEBIT,
            reference=f"Repayment Loan #{self.loan.id}",
            loan=self.loan
        )
        LedgerEntry.objects.create(
            ledger_account=self.loan_receivable,
            amount=repayment_amount,
            entry_type=LedgerEntry.EntryTypes.CREDIT,
            reference=f"Repayment Loan #{self.loan.id}",
            loan=self.loan
        )

        self.assertEqual(self.cash_account.get_balance(), repayment_amount)
        self.assertEqual(self.loan_receivable.get_balance(), -repayment_amount)

    def test_ledger_entry_immutable(self):
        entry = LedgerEntry.objects.create(
            ledger_account=self.cash_account,
            amount=Decimal("100.00"),
            entry_type=LedgerEntry.EntryTypes.DEBIT,
            reference="Test immutability",
            loan=self.loan
        )

        entry.amount = Decimal("200.00")
        with self.assertRaises(Exception):
            entry.save()

        with self.assertRaises(Exception):
            entry.delete()
