from django.contrib import admin
from .models import FinancialInstitution

@admin.register(FinancialInstitution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ('legal_name', 'license_number', 'license_status', 'regulator')
    list_filter = ('license_status', 'regulator')
    search_fields = ('legal_name', 'license_number')
