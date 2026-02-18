# core/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

class Location(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self) -> str:
        return self.name


class Organization(models.Model):
    TYPE_CHOICES = [
        ("municipality", "Gemeente"),
        ("other", "Overige organisatie"),
    ]

    organization_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    name = models.CharField(max_length=255)

    def __str__(self):
        if self.organization_type == "municipality":
            # voorkom dubbele "Gemeente Gemeente Amsterdam"
            if self.name.lower().startswith("gemeente "):
                return self.name
            return f"Gemeente {self.name}"
        return self.name


class ContactPerson(models.Model):
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.name


class BenefitType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self) -> str:
        return self.name


class Person(models.Model):
    TYPE_CHOICES = [
        ("student", "Student"),
        ("employee", "Medewerker"),
    ]

    person_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="student")

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=150)

    birth_date = models.DateField(null=True, blank=True)

    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)

    address_line = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=100, blank=True)

    # NOTE: BSN/IBAN are sensitive. Later: restrict access + consider encryption.
    bsn = models.CharField(max_length=20, blank=True)
    iban = models.CharField(max_length=34, blank=True)

    notes = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"


class StudentProfile(models.Model):
    STATUS_CHOICES = [
        ("pending", "Nog beginnen"),
        ("active", "Actief"),
        ("dropped", "Afgevallen"),
        ("completed", "Afgerond"),
    ]

    person = models.OneToOneField(Person, on_delete=models.CASCADE, related_name="student_profile")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    cv_file = models.FileField(upload_to="students/cv/", null=True, blank=True)

    job_guarantee = models.BooleanField(default=False)

    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.SET_NULL)

    # UWV / Gemeente X / Overige organisatie
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.SET_NULL)
    contact_person = models.ForeignKey(ContactPerson, null=True, blank=True, on_delete=models.SET_NULL)

    has_benefit = models.BooleanField(default=False)
    benefit_type = models.ForeignKey(BenefitType, null=True, blank=True, on_delete=models.SET_NULL)

    doelgroepregister = models.BooleanField(default=False)
    praktijkroute = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"Student: {self.person}"


class EmployeeProfile(models.Model):
    person = models.OneToOneField(Person, on_delete=models.CASCADE, related_name="employee_profile")

    hired_date = models.DateField(null=True, blank=True)
    job_title = models.CharField(max_length=100, blank=True)

    def __str__(self) -> str:
        return f"Medewerker: {self.person}"


class StudentDocument(models.Model):
    DOC_TYPE_CHOICES = [
        ("praktijkroute", "Praktijkroute"),
        ("other", "Overig"),
    ]

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES, default="other")
    file = models.FileField(upload_to="students/docs/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.get_doc_type_display()} - {self.student.person}"

class SignalCategory(models.Model):
    key = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Signal(models.Model):
    STATUS_CHOICES = [
        ("open", "Open"),
        ("done", "Afgerond"),
        ("snoozed", "Gepauzeerd"),
    ]

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="signals")
    category = models.ForeignKey(SignalCategory, on_delete=models.PROTECT, related_name="signals")

    title = models.CharField(max_length=150)
    body = models.TextField()

    active_from = models.DateTimeField(default=timezone.now)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_signals",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_signals",
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    notify = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-active_from", "-created_at"]

    def __str__(self):
        return f"{self.person} - {self.title}"


# Proxy models for clean Admin separation
class Student(Person):
    class Meta:
        proxy = True
        verbose_name = "Student"
        verbose_name_plural = "Studenten"


class Employee(Person):
    class Meta:
        proxy = True
        verbose_name = "Medewerker"
        verbose_name_plural = "Medewerkers"
class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)

    # Link terug naar de oorzaak (Signal)
    signal = models.ForeignKey(
        "Signal",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notifications",
    )

    url = models.CharField(max_length=255, blank=True)  # bv. /students/12/?tab=signals

    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_read", "-created_at"]

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])

class SignalNote(models.Model):
    signal = models.ForeignKey("Signal", on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Note for {self.signal_id}"

class SignalHistory(models.Model):
    signal = models.ForeignKey("Signal", on_delete=models.CASCADE, related_name="history")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=60)  # e.g. updated, reassigned, status_changed
    changes = models.JSONField(default=dict, blank=True)  # {"title": ["old","new"], ...}
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.signal_id} {self.action}"

class WorkPackage(models.Model):
    code = models.CharField(max_length=10, unique=True)  # "1", "1.1", "2.4"
    title = models.CharField(max_length=120)
    parent = models.ForeignKey(
        "self",
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="children"
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "code"]

    def __str__(self):
        return f"{self.code} — {self.title}"



class Roster(models.Model):
    person = models.ForeignKey("Person", on_delete=models.CASCADE, related_name="rosters")
    start_date = models.DateField()
    end_date = models.DateField()

    # ✅ bepaalt welke week "A" is
    cycle_start_date = models.DateField(null=True, blank=True)

    # ✅ Week A
    mon_a_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    tue_a_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    wed_a_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    thu_a_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    fri_a_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    sat_a_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    sun_a_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))

    # ✅ Week B
    mon_b_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    tue_b_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    wed_b_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    thu_b_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    fri_b_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    sat_b_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    sun_b_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

class RosterDay(models.Model):
    STATUS_CHOICES = [
        ("work", "Werken"),
        ("sick", "Ziek"),
        ("vacation", "Vakantie"),
        ("off", "Vrij"),
        ("swapped", "Geruild"),
        ("absent", "Ongeoorloofd afwezig"),
        ("other", "Anders"),
    ]

    person = models.ForeignKey("core.Person", on_delete=models.CASCADE, related_name="roster_days")
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="work")

    planned_hours = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    actual_hours = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["person", "date"], name="uniq_person_date_rosterday")
        ]
        ordering = ["-date"]

class RosterDayWork(models.Model):
    person = models.ForeignKey("core.Person", on_delete=models.CASCADE, related_name="day_work")
    date = models.DateField()
    work_package = models.ForeignKey("core.WorkPackage", on_delete=models.PROTECT)
    hours = models.DecimalField(max_digits=4, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["person", "date", "work_package"], name="uniq_person_date_wp")
        ]
        ordering = ["date", "work_package__sort_order", "work_package__code"]

