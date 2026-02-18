# core/admin.py
from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone

from .models import (
    Person, Student, Employee,
    StudentProfile, EmployeeProfile, StudentDocument,
    Location, Organization, ContactPerson, BenefitType
)


# --- Inlines ---

class StudentProfileInline(admin.StackedInline):
    model = StudentProfile
    extra = 0
    can_delete = True


class EmployeeProfileInline(admin.StackedInline):
    model = EmployeeProfile
    extra = 0
    can_delete = True


class ReadOnlyStudentProfileInline(admin.StackedInline):
    """
    Shows student history on an employee, but prevents editing.
    """
    model = StudentProfile
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in StudentProfile._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False


# --- Actions ---

@admin.action(description="Zet geselecteerde studenten om naar medewerker (bewaar studentdata)")
def convert_students_to_employees(modeladmin, request, queryset):
    converted = 0
    skipped = 0

    with transaction.atomic():
        for person in queryset.select_related():
            if person.person_type != "student":
                skipped += 1
                continue

            if not hasattr(person, "student_profile"):
                skipped += 1
                continue

            # Mark the student trajectory as completed (keep all student data)
            person.student_profile.status = "completed"
            if not person.student_profile.end_date:
                person.student_profile.end_date = timezone.now().date()
            person.student_profile.save()

            # Switch current type
            person.person_type = "employee"
            person.full_clean()
            person.save()

            # Create employee profile if missing
            if not hasattr(person, "employee_profile"):
                EmployeeProfile.objects.create(
                    person=person,
                    hired_date=timezone.now().date(),
                    job_title="",
                )

            converted += 1

    if converted:
        modeladmin.message_user(
            request,
            f"{converted} student(en) omgezet naar medewerker.",
            level=messages.SUCCESS,
        )
    if skipped:
        modeladmin.message_user(
            request,
            f"{skipped} overgeslagen (geen student / mist studentprofiel).",
            level=messages.WARNING,
        )


# --- Proxy Admins ---

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "email", "phone")
    search_fields = ("first_name", "last_name", "email", "phone")
    actions = [convert_students_to_employees]
    inlines = [StudentProfileInline]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(person_type="student")

    def save_model(self, request, obj, form, change):
        obj.person_type = "student"
        obj.full_clean()
        super().save_model(request, obj, form, change)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "email", "phone")
    search_fields = ("first_name", "last_name", "email", "phone")
    inlines = [EmployeeProfileInline, ReadOnlyStudentProfileInline]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(person_type="employee")

    def save_model(self, request, obj, form, change):
        obj.person_type = "employee"
        obj.full_clean()
        super().save_model(request, obj, form, change)


# Hide the raw Person so you don't accidentally use it.
try:
    admin.site.unregister(Person)
except admin.sites.NotRegistered:
    pass


# --- Lookup tables ---
admin.site.register(Location)
admin.site.register(Organization)
admin.site.register(ContactPerson)
admin.site.register(BenefitType)

# Docs registered separately (Django admin can't do nested inlines cleanly)
admin.site.register(StudentDocument)
