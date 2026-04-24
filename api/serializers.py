from decimal import Decimal

from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from customers.models import Customer, CustomerConsent
from institutions.models import Employee, FinancialInstitution
from ledger.models import LedgerAccount, LedgerEntry
from loans.models import Loan, LoanApplication, LoanProduct
from payments.models import LoanPayment

User = get_user_model()


def loan_expected_total_repayment(loan: Loan) -> Decimal:
    """Align with borrower dashboard: principal * (1 + rate/100) * (tenor_months/12)."""
    p = loan.principal_amount
    r = loan.interest_rate
    m = loan.tenure_months
    return (p * (Decimal("1") + r / Decimal("100")) * (Decimal(m) / Decimal("12"))).quantize(
        Decimal("0.01")
    )


class StaffAuthTokenSerializer(serializers.Serializer):
    """
    Staff token login: accept Django username or email.
    Default AuthTokenSerializer only checks USERNAME_FIELD; superusers often log in with email
    while their username differs (e.g. createsuperuser).
    """

    username = serializers.CharField(label="Username or email", write_only=True)
    password = serializers.CharField(
        label="Password",
        style={"input_type": "password"},
        trim_whitespace=False,
        write_only=True,
    )

    def validate(self, attrs):
        username = (attrs.get("username") or "").strip()
        password = attrs.get("password")

        if not username or not password:
            raise serializers.ValidationError(
                'Must include "username" and "password".',
                code="authorization",
            )

        auth_username = username
        if "@" in username:
            u = User.objects.filter(email__iexact=username).first()
            if u is not None:
                auth_username = u.username

        user = authenticate(
            request=self.context.get("request"),
            username=auth_username,
            password=password,
        )
        if not user:
            raise serializers.ValidationError(
                "Unable to log in with provided credentials.",
                code="authorization",
            )

        attrs["user"] = user
        return attrs


class UserSelfSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("first_name", "last_name")


class CustomerRegisterSerializer(serializers.Serializer):
    """Minimal borrower sign-up; profile/KYC completed later (apply flow or dashboard)."""

    fullName = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        e = value.strip().lower()
        if User.objects.filter(email__iexact=e).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        if User.objects.filter(username__iexact=e).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return e


PRODUCT_SLUG_TO_CODE = {
    "educredit": LoanProduct.Code.EDU,
    "youthcredit": LoanProduct.Code.YOUTH,
    "quickcredit": LoanProduct.Code.QUICK,
    "ecocredit": LoanProduct.Code.ECO,
}


class LoanProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanProduct
        fields = (
            "id",
            "name",
            "code",
            "description",
            "min_amount",
            "max_amount",
            "max_tenure_days",
            "interest_rate",
            "is_active",
            "created_at",
        )
        read_only_fields = fields


class ApplicationSubmitSerializer(serializers.Serializer):
    fullName = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20)
    dateOfBirth = serializers.DateField()
    ghanaCardNumber = serializers.CharField(max_length=20)
    isStudent = serializers.BooleanField(required=False, default=False)
    schoolName = serializers.CharField(max_length=255, allow_blank=True, required=False, default="")
    emergencyName = serializers.CharField(max_length=255)
    emergencyPhone = serializers.CharField(max_length=20)
    emergencyRelation = serializers.CharField(max_length=100)
    selectedProduct = serializers.ChoiceField(
        choices=["educredit", "youthcredit", "quickcredit", "ecocredit"]
    )
    loanAmount = serializers.CharField(max_length=32)
    loanPurpose = serializers.CharField(max_length=500)
    termsAccepted = serializers.BooleanField()

    def validate_termsAccepted(self, value):
        if not value:
            raise serializers.ValidationError("You must accept the terms.")
        return value

    def validate_loanAmount(self, value):
        try:
            d = Decimal(value)
        except Exception as exc:
            raise serializers.ValidationError("Invalid amount.") from exc
        if d <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        return value


class LoanApplicationListSerializer(serializers.ModelSerializer):
    product_code = serializers.CharField(source="product.code", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    customer_name = serializers.SerializerMethodField()
    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone_number", read_only=True)
    national_id_number = serializers.CharField(source="customer.national_id_number", read_only=True)
    loan_id = serializers.SerializerMethodField()

    class Meta:
        model = LoanApplication
        fields = (
            "id",
            "customer_name",
            "customer_email",
            "customer_phone",
            "national_id_number",
            "product_code",
            "product_name",
            "requested_amount",
            "tenure_days",
            "status",
            "created_at",
            "updated_at",
            "submitted_at",
            "decided_at",
            "loan_id",
        )
        read_only_fields = fields

    def get_customer_name(self, obj):
        u = obj.customer.user
        name = f"{u.first_name} {u.last_name}".strip()
        return name or u.username

    def get_loan_id(self, obj):
        try:
            return obj.loan.pk
        except ObjectDoesNotExist:
            return None


class LoanApplicationStaffUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanApplication
        fields = ("status",)
        extra_kwargs = {"status": {"required": True}}


class LoanListSerializer(serializers.ModelSerializer):
    product_code = serializers.CharField(source="application.product.code", read_only=True)
    customer_name = serializers.SerializerMethodField()
    application_id = serializers.IntegerField(source="application.id", read_only=True)
    total_paid = serializers.SerializerMethodField()
    total_repayment_due = serializers.SerializerMethodField()
    outstanding_balance = serializers.SerializerMethodField()

    class Meta:
        model = Loan
        fields = (
            "id",
            "application_id",
            "customer_name",
            "product_code",
            "principal_amount",
            "interest_rate",
            "tenure_months",
            "status",
            "disbursed_at",
            "maturity_date",
            "created_at",
            "total_paid",
            "total_repayment_due",
            "outstanding_balance",
        )
        read_only_fields = fields

    def get_customer_name(self, obj):
        u = obj.application.customer.user
        name = f"{u.first_name} {u.last_name}".strip()
        return name or u.username

    def get_total_paid(self, obj):
        t = (
            obj.payments.filter(status=LoanPayment.Status.COMPLETED).aggregate(s=Sum("amount"))["s"]
            or Decimal("0")
        )
        return str(t.quantize(Decimal("0.01")))

    def get_total_repayment_due(self, obj):
        return str(loan_expected_total_repayment(obj))

    def get_outstanding_balance(self, obj):
        due = loan_expected_total_repayment(obj)
        paid = (
            obj.payments.filter(status=LoanPayment.Status.COMPLETED).aggregate(s=Sum("amount"))["s"]
            or Decimal("0")
        )
        out = max(Decimal("0"), due - paid)
        return str(out.quantize(Decimal("0.01")))


class DisburseLoanSerializer(serializers.Serializer):
    application_id = serializers.IntegerField(min_value=1)
    principal_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    disbursed_at = serializers.DateTimeField(required=False, allow_null=True)
    tenure_months = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    maturity_date = serializers.DateField(required=False, allow_null=True)


class CustomerPaymentCreateSerializer(serializers.Serializer):
    loan_id = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    method = serializers.ChoiceField(
        choices=LoanPayment.Method.choices, default=LoanPayment.Method.MOMO
    )
    reference = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class StaffLoanPaymentSerializer(serializers.ModelSerializer):
    loan_id = serializers.IntegerField(source="loan.id", read_only=True)
    customer_name = serializers.SerializerMethodField()

    class Meta:
        model = LoanPayment
        fields = (
            "id",
            "loan_id",
            "customer_name",
            "amount",
            "paid_at",
            "method",
            "reference",
            "status",
            "created_at",
        )
        read_only_fields = fields

    def get_customer_name(self, obj):
        u = obj.loan.application.customer.user
        name = f"{u.first_name} {u.last_name}".strip()
        return name or u.username


class StaffRecordPaymentSerializer(serializers.Serializer):
    loan_id = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    method = serializers.ChoiceField(choices=LoanPayment.Method.choices, default=LoanPayment.Method.CASH)
    reference = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    paid_at = serializers.DateTimeField(required=False, allow_null=True)


class LedgerAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerAccount
        fields = ("id", "name", "account_type", "is_active", "created_at")
        read_only_fields = fields


class LedgerEntrySerializer(serializers.ModelSerializer):
    ledger_account_name = serializers.CharField(source="ledger_account.name", read_only=True)

    class Meta:
        model = LedgerEntry
        fields = (
            "id",
            "ledger_account",
            "ledger_account_name",
            "amount",
            "entry_type",
            "reference",
            "loan",
            "created_at",
        )
        read_only_fields = fields


class CollectionsLoanSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    customer_phone = serializers.CharField(source="application.customer.phone_number", read_only=True)
    customer_email = serializers.EmailField(source="application.customer.email", read_only=True)
    product_code = serializers.CharField(source="application.product.code", read_only=True)
    outstanding_balance = serializers.SerializerMethodField()

    class Meta:
        model = Loan
        fields = (
            "id",
            "customer_name",
            "customer_phone",
            "customer_email",
            "product_code",
            "principal_amount",
            "status",
            "disbursed_at",
            "maturity_date",
            "outstanding_balance",
        )
        read_only_fields = fields

    def get_customer_name(self, obj):
        u = obj.application.customer.user
        name = f"{u.first_name} {u.last_name}".strip()
        return name or u.username

    def get_outstanding_balance(self, obj):
        due = loan_expected_total_repayment(obj)
        paid = (
            obj.payments.filter(status=LoanPayment.Status.COMPLETED).aggregate(s=Sum("amount"))["s"]
            or Decimal("0")
        )
        return str(max(Decimal("0"), due - paid).quantize(Decimal("0.01")))


class FinancialInstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialInstitution
        fields = (
            "id",
            "legal_name",
            "trading_name",
            "company_registration_number",
            "license_number",
            "license_status",
            "institution_type",
            "is_active",
        )
        read_only_fields = fields


class EmployeeListSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)

    class Meta:
        model = Employee
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_active",
            "created_at",
        )
        read_only_fields = fields


class StaffEmployeeCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, required=False, default="")
    last_name = serializers.CharField(max_length=150, required=False, default="")
    role = serializers.ChoiceField(choices=Employee.Role.choices)


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = (
            "id",
            "national_id_type",
            "national_id_number",
            "date_of_birth",
            "phone_number",
            "email",
            "residential_address",
            "occupation",
            "monthly_income",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "national_id_number", "created_at", "updated_at")


class CustomerUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = (
            "phone_number",
            "residential_address",
            "occupation",
            "monthly_income",
        )


class MeSerializer(serializers.Serializer):
    user = serializers.DictField(read_only=True)
    customer = CustomerSerializer(read_only=True, allow_null=True)
    applications = LoanApplicationListSerializer(many=True, read_only=True)
    loans = LoanListSerializer(many=True, read_only=True)


def split_full_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def create_application_from_validated(validated: dict) -> LoanApplication:
    code = PRODUCT_SLUG_TO_CODE[validated["selectedProduct"]]
    product = LoanProduct.objects.get(code=code)
    amount = Decimal(validated["loanAmount"])
    if amount < product.min_amount or amount > product.max_amount:
        raise serializers.ValidationError(
            {"loanAmount": f"Amount must be between {product.min_amount} and {product.max_amount}."}
        )

    tenure_days = min(int(product.max_tenure_days), 180)
    if tenure_days < 1:
        tenure_days = 30

    first, last = split_full_name(validated["fullName"])
    email = validated["email"].strip().lower()

    with transaction.atomic():
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            user = User(
                username=email,
                email=email,
                first_name=first[:150],
                last_name=last[:150],
                type=User.UserType.CUSTOMER,
            )
            user.set_unusable_password()
            user.save()
        else:
            if not user.is_customer():
                raise serializers.ValidationError(
                    {"email": "This email is already registered with a different account type."}
                )
            if first:
                user.first_name = first[:150]
            if last:
                user.last_name = last[:150]
            user.save(update_fields=["first_name", "last_name"])

        national_id = validated["ghanaCardNumber"].strip().upper()

        existing_by_card = Customer.objects.filter(national_id_number=national_id).first()
        if existing_by_card and existing_by_card.user_id != user.id:
            raise serializers.ValidationError(
                {"ghanaCardNumber": "This Ghana Card is already linked to another account."}
            )

        if hasattr(user, "customer_profile"):
            customer = user.customer_profile
            profile_id = customer.national_id_number.strip().upper()
            pending_profile = profile_id.startswith("PENDING-")
            if not pending_profile and profile_id != national_id:
                raise serializers.ValidationError(
                    {"ghanaCardNumber": "Ghana Card does not match the profile for this email."}
                )
            customer.phone_number = validated["phone"].strip()
            customer.email = email
            customer.date_of_birth = validated["dateOfBirth"]
            update_fields = ["phone_number", "email", "date_of_birth"]
            if pending_profile:
                customer.national_id_number = national_id
                update_fields.append("national_id_number")
            customer.save(update_fields=update_fields)
        else:
            customer = Customer.objects.create(
                user=user,
                national_id_type=Customer.IDType.GHANACARD,
                national_id_number=national_id,
                date_of_birth=validated["dateOfBirth"],
                phone_number=validated["phone"].strip(),
                email=email,
                residential_address="Provided at application — update in profile",
                occupation="Applicant",
                monthly_income=Decimal("0.00"),
                status=Customer.Status.ACTIVE,
            )

        application = LoanApplication.objects.create(
            customer=customer,
            product=product,
            requested_amount=amount,
            tenure_days=tenure_days,
            status=LoanApplication.Status.SUBMITTED,
            submitted_at=timezone.now(),
        )

        CustomerConsent.objects.get_or_create(
            customer=customer,
            consent_type=CustomerConsent.ConsentType.TERMS_AND_CONDITIONS,
            version="2025-01",
            defaults={},
        )

    return application
