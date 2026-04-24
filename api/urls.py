from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ApplicationSubmitView,
    CustomerObtainAuthToken,
    CustomerPaymentCreateView,
    CustomerRegisterView,
    CustomerRecordViewSet,
    CustomerSelfDetailView,
    LedgerAccountViewSet,
    LedgerEntryViewSet,
    LoanApplicationViewSet,
    LoanProductViewSet,
    LoanViewSet,
    MeView,
    StaffAnalyticsSummaryView,
    StaffCollectionsLoansView,
    StaffDashboardSummaryView,
    StaffEmployeeViewSet,
    StaffInstitutionView,
    StaffLoanDisburseView,
    StaffLoanPaymentViewSet,
    StaffMeView,
    StaffObtainAuthToken,
    UserSelfDetailView,
)

router = DefaultRouter()
router.register(r"products", LoanProductViewSet, basename="loanproduct")
router.register(r"staff/applications", LoanApplicationViewSet, basename="staff-application")
router.register(r"staff/loans", LoanViewSet, basename="staff-loan")
router.register(r"staff/customers", CustomerRecordViewSet, basename="staff-customer")
router.register(r"staff/payments", StaffLoanPaymentViewSet, basename="staff-payment")
router.register(r"staff/ledger/accounts", LedgerAccountViewSet, basename="ledger-account")
router.register(r"staff/ledger/entries", LedgerEntryViewSet, basename="ledger-entry")
router.register(r"staff/employees", StaffEmployeeViewSet, basename="staff-employee")

urlpatterns = [
    path("staff/loans/disburse/", StaffLoanDisburseView.as_view()),
    path("staff/dashboard-summary/", StaffDashboardSummaryView.as_view()),
    path("staff/analytics/summary/", StaffAnalyticsSummaryView.as_view()),
    path("staff/collections/loans/", StaffCollectionsLoansView.as_view()),
    path("staff/institution/", StaffInstitutionView.as_view()),
    path("me/staff/", StaffMeView.as_view()),
    path("me/payments/", CustomerPaymentCreateView.as_view()),
    path("applications/submit/", ApplicationSubmitView.as_view()),
    path("auth/customer-register/", CustomerRegisterView.as_view()),
    path("auth/staff-token/", StaffObtainAuthToken.as_view()),
    path("auth/customer-token/", CustomerObtainAuthToken.as_view()),
    path("me/", MeView.as_view()),
    path("me/user/", UserSelfDetailView.as_view()),
    path("me/customer/", CustomerSelfDetailView.as_view()),
    path("", include(router.urls)),
]
