from datetime import date, timedelta
from decimal import Decimal

import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework import mixins, serializers as drf_serializers, status, viewsets
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from customers.models import Customer, CustomerConsent
from institutions.models import Employee, FinancialInstitution
from ledger.models import LedgerAccount, LedgerEntry
from loans.models import Loan, LoanApplication, LoanProduct
from payments.models import LoanPayment

from .permissions import IsCustomerUser, IsStaffUser
from .serializers import (
    ApplicationSubmitSerializer,
    CollectionsLoanSerializer,
    CustomerPaymentCreateSerializer,
    CustomerRegisterSerializer,
    CustomerSerializer,
    CustomerUpdateSerializer,
    DisburseLoanSerializer,
    EmployeeListSerializer,
    FinancialInstitutionSerializer,
    LedgerAccountSerializer,
    LedgerEntrySerializer,
    LoanApplicationListSerializer,
    LoanApplicationStaffUpdateSerializer,
    LoanListSerializer,
    LoanProductSerializer,
    StaffAuthTokenSerializer,
    StaffEmployeeCreateSerializer,
    StaffLoanPaymentSerializer,
    StaffRecordPaymentSerializer,
    UserSelfSerializer,
    create_application_from_validated,
    loan_expected_total_repayment,
    split_full_name,
)

User = get_user_model()


class CustomerRegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        ser = CustomerRegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        first, last = split_full_name(d["fullName"])
        email = d["email"]
        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                email=email,
                password=d["password"],
                first_name=first[:150],
                last_name=last[:150],
                type=User.UserType.CUSTOMER,
            )
            pending_id = f"PENDING-{uuid.uuid4().hex}"[:50]
            Customer.objects.create(
                user=user,
                national_id_type=Customer.IDType.GHANACARD,
                national_id_number=pending_id,
                date_of_birth=date(1990, 1, 1),
                phone_number="0000000000",
                email=email,
                residential_address="Complete your profile after sign-up",
                occupation="Pending",
                monthly_income=Decimal("0.00"),
                status=Customer.Status.ACTIVE,
            )
            CustomerConsent.objects.get_or_create(
                customer=user.customer_profile,
                consent_type=CustomerConsent.ConsentType.TERMS_AND_CONDITIONS,
                version="2025-01",
                defaults={},
            )
            token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key}, status=status.HTTP_201_CREATED)


class ApplicationSubmitView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        ser = ApplicationSubmitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            application = create_application_from_validated(ser.validated_data)
        except drf_serializers.ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        out = LoanApplicationListSerializer(application).data
        return Response(out, status=status.HTTP_201_CREATED)


class LoanProductViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    queryset = LoanProduct.objects.filter(is_active=True).order_by("name")
    serializer_class = LoanProductSerializer


class LoanApplicationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, IsStaffUser]
    queryset = LoanApplication.objects.select_related(
        "customer", "customer__user", "product"
    ).prefetch_related("loan").order_by("-created_at")
    serializer_class = LoanApplicationListSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.action in ("partial_update", "update"):
            return LoanApplicationStaffUpdateSerializer
        return LoanApplicationListSerializer

    def perform_update(self, serializer):
        instance = serializer.save()
        if "status" in serializer.validated_data:
            st = serializer.validated_data["status"]
            if st in (
                LoanApplication.Status.APPROVED,
                LoanApplication.Status.REJECTED,
                LoanApplication.Status.CANCELLED,
            ):
                instance.decided_at = timezone.now()
                instance.save(update_fields=["decided_at"])


class LoanViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, IsStaffUser]
    queryset = (
        Loan.objects.select_related(
            "application", "application__customer", "application__customer__user", "application__product"
        )
        .prefetch_related("payments")
        .order_by("-created_at")
    )
    serializer_class = LoanListSerializer


def _post_repayment_ledger(loan: Loan, amount: Decimal) -> None:
    recv, _ = LedgerAccount.objects.get_or_create(
        name="Loan Receivable",
        defaults={"account_type": LedgerAccount.AccountTypes.ASSET},
    )
    cash, _ = LedgerAccount.objects.get_or_create(
        name="Cash/Bank",
        defaults={"account_type": LedgerAccount.AccountTypes.ASSET},
    )
    ref = f"Repayment Loan #{loan.id}"
    LedgerEntry.objects.create(
        ledger_account=cash,
        amount=amount,
        entry_type=LedgerEntry.EntryTypes.DEBIT,
        reference=ref,
        loan=loan,
    )
    LedgerEntry.objects.create(
        ledger_account=recv,
        amount=amount,
        entry_type=LedgerEntry.EntryTypes.CREDIT,
        reference=ref,
        loan=loan,
    )


def _post_disbursement_ledger(loan: Loan) -> None:
    recv, _ = LedgerAccount.objects.get_or_create(
        name="Loan Receivable",
        defaults={"account_type": LedgerAccount.AccountTypes.ASSET},
    )
    cash, _ = LedgerAccount.objects.get_or_create(
        name="Cash/Bank",
        defaults={"account_type": LedgerAccount.AccountTypes.ASSET},
    )
    ref = f"Disbursement Loan #{loan.id}"
    LedgerEntry.objects.create(
        ledger_account=recv,
        amount=loan.principal_amount,
        entry_type=LedgerEntry.EntryTypes.DEBIT,
        reference=ref,
        loan=loan,
    )
    LedgerEntry.objects.create(
        ledger_account=cash,
        amount=loan.principal_amount,
        entry_type=LedgerEntry.EntryTypes.CREDIT,
        reference=ref,
        loan=loan,
    )


class StaffLoanDisburseView(APIView):
    """Create a Loan for an APPROVED application (explicit disbursement)."""

    permission_classes = [IsAuthenticated, IsStaffUser]

    def post(self, request):
        ser = DisburseLoanSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        app_id = data["application_id"]

        with transaction.atomic():
            application = (
                LoanApplication.objects.select_for_update()
                .select_related("product", "customer")
                .filter(pk=app_id)
                .first()
            )
            if application is None:
                return Response(
                    {"detail": "Application not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if application.status != LoanApplication.Status.APPROVED:
                return Response(
                    {"detail": "Only APPROVED applications can be disbursed."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if Loan.objects.filter(application=application).exists():
                return Response(
                    {"detail": "This application is already disbursed."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            principal = data.get("principal_amount") or application.requested_amount
            if principal <= 0:
                return Response(
                    {"detail": "principal_amount must be positive."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            disbursed_at = data.get("disbursed_at") or timezone.now()
            tenure_months = data.get("tenure_months")
            if tenure_months is None:
                tenure_months = max(1, (application.tenure_days + 29) // 30)

            maturity_date = data.get("maturity_date")
            if maturity_date is None:
                maturity_date = (disbursed_at + timedelta(days=application.tenure_days)).date()

            loan = Loan.objects.create(
                application=application,
                principal_amount=principal,
                interest_rate=application.product.interest_rate,
                tenure_months=tenure_months,
                status=Loan.Status.ACTIVE,
                disbursed_at=disbursed_at,
                maturity_date=maturity_date,
            )
            _post_disbursement_ledger(loan)

        out = LoanListSerializer(loan).data
        return Response(out, status=status.HTTP_201_CREATED)


def _loan_total_paid(loan: Loan) -> Decimal:
    t = (
        LoanPayment.objects.filter(loan=loan, status=LoanPayment.Status.COMPLETED).aggregate(
            s=Sum("amount")
        )["s"]
        or Decimal("0")
    )
    return t


def _maybe_complete_loan(loan: Loan) -> None:
    due = loan_expected_total_repayment(loan)
    paid = _loan_total_paid(loan)
    if loan.status == Loan.Status.ACTIVE and paid >= due:
        loan.status = Loan.Status.COMPLETED
        loan.save(update_fields=["status"])


class CustomerPaymentCreateView(APIView):
    permission_classes = [IsAuthenticated, IsCustomerUser]

    def post(self, request):
        ser = CustomerPaymentCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        customer = request.user.customer_profile
        loan = (
            Loan.objects.select_related("application__customer")
            .filter(pk=d["loan_id"], application__customer=customer)
            .first()
        )
        if loan is None:
            return Response({"detail": "Loan not found."}, status=status.HTTP_404_NOT_FOUND)
        if loan.status != Loan.Status.ACTIVE:
            return Response(
                {"detail": "Payments are only accepted on active loans."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        amount = d["amount"]
        due = loan_expected_total_repayment(loan)
        paid_so_far = _loan_total_paid(loan)
        outstanding = due - paid_so_far
        if amount <= 0:
            return Response({"detail": "Amount must be positive."}, status=status.HTTP_400_BAD_REQUEST)
        if amount > outstanding:
            return Response(
                {"detail": "Amount exceeds outstanding balance."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            payment = LoanPayment.objects.create(
                loan=loan,
                amount=amount,
                paid_at=timezone.now(),
                method=d["method"],
                reference=d.get("reference") or "",
                status=LoanPayment.Status.COMPLETED,
                recorded_by=None,
            )
            _post_repayment_ledger(loan, amount)
            _maybe_complete_loan(loan)
        return Response(StaffLoanPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class StaffLoanPaymentViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsStaffUser]
    queryset = LoanPayment.objects.select_related(
        "loan", "loan__application", "loan__application__customer", "loan__application__customer__user"
    ).order_by("-paid_at", "-id")

    def get_serializer_class(self):
        if self.action == "create":
            return StaffRecordPaymentSerializer
        return StaffLoanPaymentSerializer

    def create(self, request, *args, **kwargs):
        ser = StaffRecordPaymentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        loan = Loan.objects.select_related("application__customer").filter(pk=d["loan_id"]).first()
        if loan is None:
            return Response({"detail": "Loan not found."}, status=status.HTTP_404_NOT_FOUND)
        if loan.status not in (Loan.Status.ACTIVE, Loan.Status.DEFAULTED):
            return Response(
                {"detail": "Payments can only be recorded for active or defaulted loans."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        amount = d["amount"]
        due = loan_expected_total_repayment(loan)
        paid_so_far = _loan_total_paid(loan)
        outstanding = due - paid_so_far
        if amount <= 0:
            return Response({"detail": "Amount must be positive."}, status=status.HTTP_400_BAD_REQUEST)
        if amount > outstanding:
            return Response(
                {"detail": "Amount exceeds outstanding balance."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        paid_at = d.get("paid_at") or timezone.now()
        with transaction.atomic():
            payment = LoanPayment.objects.create(
                loan=loan,
                amount=amount,
                paid_at=paid_at,
                method=d["method"],
                reference=d.get("reference") or "",
                status=LoanPayment.Status.COMPLETED,
                recorded_by=request.user,
            )
            _post_repayment_ledger(loan, amount)
            _maybe_complete_loan(loan)
        return Response(
            StaffLoanPaymentSerializer(payment).data,
            status=status.HTTP_201_CREATED,
        )


class CustomerRecordViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, IsStaffUser]
    queryset = Customer.objects.select_related("user").order_by("-created_at")
    serializer_class = CustomerSerializer


class MeView(APIView):
    permission_classes = [IsAuthenticated, IsCustomerUser]

    def get(self, request):
        user = request.user
        customer = user.customer_profile
        apps = (
            LoanApplication.objects.filter(customer=customer)
            .select_related("product")
            .prefetch_related("loan")
        )
        loans_qs = (
            Loan.objects.filter(application__customer=customer)
            .select_related("application", "application__product", "application__customer__user")
            .prefetch_related("payments")
        )
        data = {
            "user": {
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
            "customer": CustomerSerializer(customer).data,
            "applications": LoanApplicationListSerializer(apps, many=True).data,
            "loans": LoanListSerializer(loans_qs, many=True).data,
        }
        return Response(data)


class UserSelfDetailView(APIView):
    permission_classes = [IsAuthenticated, IsCustomerUser]

    def patch(self, request):
        ser = UserSelfSerializer(request.user, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(UserSelfSerializer(request.user).data)


class CustomerSelfDetailView(APIView):
    permission_classes = [IsAuthenticated, IsCustomerUser]

    def get(self, request):
        return Response(CustomerSerializer(request.user.customer_profile).data)

    def patch(self, request):
        ser = CustomerUpdateSerializer(
            request.user.customer_profile, data=request.data, partial=True
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(CustomerSerializer(request.user.customer_profile).data)


class StaffObtainAuthToken(ObtainAuthToken):
    """Token auth for staff; requires is_staff, superuser, or institutions.Employee."""

    serializer_class = StaffAuthTokenSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        if not (user.is_superuser or user.is_staff or hasattr(user, "employee_profile")):
            return Response(
                {"detail": "Not a staff account."},
                status=status.HTTP_403_FORBIDDEN,
            )
        from rest_framework.authtoken.models import Token

        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key})


class CustomerObtainAuthToken(ObtainAuthToken):
    """Token auth for borrowers (customer_profile required)."""

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        if not hasattr(user, "customer_profile"):
            return Response(
                {"detail": "Not a customer account."},
                status=status.HTTP_403_FORBIDDEN,
            )
        from rest_framework.authtoken.models import Token

        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key})


class StaffMeView(APIView):
    permission_classes = [IsAuthenticated, IsStaffUser]

    def get(self, request):
        u = request.user
        payload = {
            "username": u.username,
            "email": u.email or "",
            "first_name": u.first_name or "",
            "last_name": u.last_name or "",
            "is_superuser": u.is_superuser,
            "is_staff": u.is_staff,
            "employee_role": None,
            "permissions": [],
        }
        if u.is_superuser:
            payload["permissions"] = ["staff", "admin", "superuser"]
        else:
            payload["permissions"] = ["staff"]
        emp = getattr(u, "employee_profile", None)
        if emp is not None:
            payload["employee_role"] = emp.role
            if emp.is_admin():
                payload["permissions"] = list(set(payload["permissions"] + ["admin"]))
        return Response(payload)


class StaffDashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsStaffUser]

    def get(self, request):
        now = timezone.now()
        start_mtd = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        disbursed_mtd = Loan.objects.filter(disbursed_at__gte=start_mtd).aggregate(
            s=Sum("principal_amount")
        )["s"] or Decimal("0")

        pending = LoanApplication.objects.filter(
            status__in=[
                LoanApplication.Status.SUBMITTED,
                LoanApplication.Status.UNDER_REVIEW,
            ]
        ).count()

        has_loan = Exists(Loan.objects.filter(application_id=OuterRef("pk")))
        approved_waiting = (
            LoanApplication.objects.filter(status=LoanApplication.Status.APPROVED)
            .annotate(_has_loan=has_loan)
            .filter(_has_loan=False)
            .count()
        )

        in_default = Loan.objects.filter(
            status__in=[Loan.Status.DEFAULTED, Loan.Status.WRITTEN_OFF]
        ).count()

        active_loans = Loan.objects.filter(status=Loan.Status.ACTIVE).prefetch_related("payments")
        total_due = Decimal("0")
        total_paid_portfolio = Decimal("0")
        for ln in active_loans:
            total_due += loan_expected_total_repayment(ln)
            total_paid_portfolio += _loan_total_paid(ln)

        if total_due > 0:
            collection_rate = float(
                (total_paid_portfolio / total_due * Decimal("100")).quantize(Decimal("0.1"))
            )
        else:
            collection_rate = 100.0

        recent = []
        for pay in (
            LoanPayment.objects.select_related(
                "loan__application__customer__user", "loan__application__product"
            )
            .order_by("-created_at")[:8]
        ):
            u = pay.loan.application.customer.user
            name = f"{u.first_name} {u.last_name}".strip() or u.username
            recent.append(
                {
                    "type": "payment",
                    "title": "Payment received",
                    "subtitle": f"{name} · GH₵{pay.amount}",
                    "at": pay.paid_at.isoformat(),
                }
            )
        for app in (
            LoanApplication.objects.select_related("customer__user", "product")
            .filter(decided_at__isnull=False)
            .order_by("-decided_at")[:5]
        ):
            if app.status == LoanApplication.Status.APPROVED:
                title = "Application approved"
            elif app.status == LoanApplication.Status.REJECTED:
                title = "Application rejected"
            else:
                title = f"Application {app.status}"
            u = app.customer.user
            name = f"{u.first_name} {u.last_name}".strip() or u.username
            dt = app.decided_at or app.updated_at
            recent.append(
                {
                    "type": "application",
                    "title": title,
                    "subtitle": f"{name} · {app.product.code}",
                    "at": dt.isoformat(),
                }
            )
        recent.sort(key=lambda x: x["at"], reverse=True)
        recent = recent[:10]

        return Response(
            {
                "total_disbursed_mtd": str(disbursed_mtd.quantize(Decimal("0.01"))),
                "pending_applications": pending,
                "approved_awaiting_disbursement": approved_waiting,
                "collection_rate_percent": collection_rate,
                "accounts_in_default": in_default,
                "quick_actions": {
                    "pending_applications": pending,
                    "accounts_in_default": in_default,
                },
                "recent_activity": recent,
            }
        )


class StaffAnalyticsSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsStaffUser]

    def get(self, request):
        by_month = (
            Loan.objects.filter(disbursed_at__isnull=False)
            .annotate(m=TruncMonth("disbursed_at"))
            .values("m")
            .annotate(total=Sum("principal_amount"), count=Count("id"))
            .order_by("m")
        )
        series = []
        for row in by_month:
            m = row["m"]
            series.append(
                {
                    "month": m.isoformat() if m else None,
                    "total": str((row["total"] or Decimal("0")).quantize(Decimal("0.01"))),
                    "count": row["count"],
                }
            )
        status_rows = Loan.objects.values("status").annotate(count=Count("id"))
        return Response(
            {
                "disbursements_by_month": series,
                "loans_by_status": list(status_rows),
            }
        )


class StaffCollectionsLoansView(APIView):
    permission_classes = [IsAuthenticated, IsStaffUser]

    def get(self, request):
        qs = (
            Loan.objects.filter(status__in=[Loan.Status.DEFAULTED, Loan.Status.WRITTEN_OFF])
            .select_related("application__customer__user", "application__product")
            .prefetch_related("payments")
            .order_by("-id")
        )
        return Response(CollectionsLoanSerializer(qs, many=True).data)


class StaffInstitutionView(APIView):
    permission_classes = [IsAuthenticated, IsStaffUser]

    def get(self, request):
        fi = FinancialInstitution.objects.filter(is_active=True).first()
        if fi is None:
            fi = FinancialInstitution.objects.first()
        if fi is None:
            return Response(
                {"detail": "No institution configured."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(FinancialInstitutionSerializer(fi).data)


class LedgerAccountViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, IsStaffUser]
    queryset = LedgerAccount.objects.all().order_by("name")
    serializer_class = LedgerAccountSerializer


class LedgerEntryViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, IsStaffUser]
    queryset = LedgerEntry.objects.select_related("ledger_account", "loan").order_by("-created_at")
    serializer_class = LedgerEntrySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        loan_id = self.request.query_params.get("loan")
        if loan_id:
            qs = qs.filter(loan_id=loan_id)
        return qs


class StaffEmployeeViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsStaffUser]
    queryset = Employee.objects.select_related("user", "institution").order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return StaffEmployeeCreateSerializer
        return EmployeeListSerializer

    def create(self, request, *args, **kwargs):
        if not (
            request.user.is_superuser
            or (
                getattr(request.user, "employee_profile", None)
                and request.user.employee_profile.is_admin()
            )
        ):
            raise PermissionDenied("Only administrators can create staff users.")
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        fi = FinancialInstitution.objects.filter(is_active=True).first()
        if fi is None:
            fi = FinancialInstitution.objects.first()
        if fi is None:
            return Response(
                {"detail": "Create a FinancialInstitution first (e.g. seed_jashfin_data)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        uname = d["username"].strip()
        email = d["email"].strip().lower()
        if User.objects.filter(username__iexact=uname).exists():
            return Response(
                {"username": ["A user with this username already exists."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if User.objects.filter(email__iexact=email).exists():
            return Response(
                {"email": ["A user with this email already exists."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            user = User.objects.create_user(
                username=uname,
                email=email,
                password=d["password"],
                first_name=(d.get("first_name") or "")[:150],
                last_name=(d.get("last_name") or "")[:150],
                type=User.UserType.EMPLOYEE,
                is_staff=True,
            )
            emp = Employee.objects.create(
                institution=fi,
                user=user,
                role=d["role"],
                is_active=True,
            )
        return Response(EmployeeListSerializer(emp).data, status=status.HTTP_201_CREATED)
