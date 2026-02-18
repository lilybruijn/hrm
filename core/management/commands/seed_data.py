# core/management/commands/seed_data.py

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from faker import Faker

from core.models import (
    Location,
    Organization,
    BenefitType,
    ContactPerson,
    Person,
    StudentProfile,
    EmployeeProfile,
    StudentDocument,
    SignalCategory,
    Signal,
)

fake = Faker("nl_NL")


class Command(BaseCommand):
    help = "Seed database with realistic fake HRM data for ALL models."

    def add_arguments(self, parser):
        parser.add_argument("--students", type=int, default=40)
        parser.add_argument("--employees", type=int, default=15)
        parser.add_argument("--docs", type=int, default=2)
        parser.add_argument("--clear", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        students_n = options["students"]
        employees_n = options["employees"]
        docs_avg = max(0, options["docs"])
        do_clear = options["clear"]

        if do_clear:
            Signal.objects.all().delete()
            SignalCategory.objects.all().delete()
            StudentDocument.objects.all().delete()
            EmployeeProfile.objects.all().delete()
            StudentProfile.objects.all().delete()
            Person.objects.all().delete()
            ContactPerson.objects.all().delete()
            Organization.objects.all().delete()
            BenefitType.objects.all().delete()
            Location.objects.all().delete()
            self.stdout.write(self.style.WARNING("Cleared existing core data."))

        # Users
        admin_user, emma_user = self._seed_users()

        # Lookup data
        categories = self._seed_signal_categories()
        locations = self._seed_locations()
        organizations = self._seed_organizations()
        benefit_types = self._seed_benefit_types()
        contact_people = self._seed_contact_people(organizations)

        # Students
        student_people = self._seed_students(
            n=students_n,
            locations=locations,
            organizations=organizations,
            contact_people=contact_people,
            benefit_types=benefit_types,
        )

        self._seed_student_documents(student_people, docs_avg)

        # Employees
        self._seed_employees(employees_n)

        # Signals
        self._seed_signals(
            people=student_people,
            categories=categories,
            created_by=admin_user,
            assignees=[admin_user, emma_user],
            per_person_avg=2,
        )

        self.stdout.write(self.style.SUCCESS("✅ Seeding completed successfully."))

    # ------------------------------------------------
    # USERS
    # ------------------------------------------------

    def _seed_users(self):
        User = get_user_model()

        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@example.com",
                "is_staff": True,
                "is_superuser": True,
            },
        )

        if not admin.is_staff or not admin.is_superuser:
            admin.is_staff = True
            admin.is_superuser = True
            admin.save(update_fields=["is_staff", "is_superuser"])

        if created:
            admin.set_password("admin12345")
            admin.save(update_fields=["password"])

        emma, created = User.objects.get_or_create(
            username="emma",
            defaults={
                "email": "emma@example.com",
                "is_staff": True,
                "is_superuser": True,
            },
        )

        if not emma.is_staff or not emma.is_superuser:
            emma.is_staff = True
            emma.is_superuser = True
            emma.save(update_fields=["is_staff", "is_superuser"])

        if created:
            emma.set_password("emma12345")
            emma.save(update_fields=["password"])

        return admin, emma

    # ------------------------------------------------
    # LOOKUPS
    # ------------------------------------------------

    def _seed_locations(self):
        names = ["Groningen", "Amsterdam"]
        return [Location.objects.get_or_create(name=n)[0] for n in names]

    def _seed_organizations(self):
        organization_specs = [
            ("other", "UWV"),
            ("municipality", "Amsterdam"),
            ("municipality", "Groningen"),
            ("other", "WerkPro"),
            ("other", "Re-integratie Noord"),
        ]
        return [
           Organization.objects.get_or_create(org_type=t, name=n)[0]
            for t, n in organization_specs
        ]

    def _seed_benefit_types(self):
        names = ["WW", "WIA", "Bijstand", "Wajong", "Ziektewet"]
        return [BenefitType.objects.get_or_create(name=n)[0] for n in names]

    def _seed_signal_categories(self):
        specs = [
            ("general", "Algemeen"),
            ("contract", "Contract"),
            ("education", "Opleiding"),
            ("praktijkroute", "Praktijkroute"),
            ("loonwaarde", "Loonwaarde (gesprek)"),
            ("lks", "Loonkostensubsidie / loondispensatie"),
            ("jobcoaching", "Jobcoaching"),
        ]
        return [
            SignalCategory.objects.get_or_create(key=k, defaults={"name": n})[0]
            for k, n in specs
        ]

    def _seed_contact_people(self, organizations):
        out = []
        for org in organizations:
            for _ in range(random.randint(1, 3)):
                out.append(
                    ContactPerson.objects.create(
                        organization=org,
                        name=fake.name(),
                        email=fake.email(),
                        phone=fake.phone_number(),
                        notes=fake.sentence(),
                    )
                )
        return out

    # ------------------------------------------------
    # STUDENTS
    # ------------------------------------------------

    def _seed_students(self, n, locations, organizations, contact_people, benefit_types):
        out = []

        for _ in range(n):
            person = Person.objects.create(
                person_type="student",
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                birth_date=fake.date_of_birth(minimum_age=18, maximum_age=60),
                email=fake.email(),
                phone=fake.phone_number(),
                address_line=fake.street_address(),
                postal_code=fake.postcode(),
                city=fake.city(),
                bsn=str(random.randint(100000000, 999999999)),
                iban=fake.iban(),
                notes=fake.sentence(),
            )

            org = random.choice(organizations)
            contact = random.choice(contact_people)

            StudentProfile.objects.create(
                person=person,
                status=random.choice(["pending", "active", "dropped"]),
                start_date=fake.date_between(start_date="-1y", end_date="today"),
                job_guarantee=random.choice([True, False]),
                location=random.choice(locations),
                organization=org,
                contact_person=contact,
                has_benefit=random.choice([True, False]),
                benefit_type=random.choice(benefit_types),
                doelgroepregister=random.choice([True, False]),
                praktijkroute=random.choice([True, False]),
            )

            out.append(person)

        return out

    def _seed_student_documents(self, students, docs_avg):
        for person in students:
            sp = person.student_profile
            count = max(0, int(random.gauss(docs_avg, 1)))

            for i in range(count):
                doc = StudentDocument.objects.create(
                    student=sp,
                    doc_type=random.choice(["other", "praktijkroute"]),
                )
                content = f"Fake doc for {person.first_name}".encode()
                doc.file.save(f"doc_{person.id}_{i}.txt", ContentFile(content), save=True)

    # ------------------------------------------------
    # EMPLOYEES
    # ------------------------------------------------

    def _seed_employees(self, n):
        for _ in range(n):
            person = Person.objects.create(
                person_type="employee",
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                birth_date=fake.date_of_birth(minimum_age=18, maximum_age=60),
                email=fake.email(),
                phone=fake.phone_number(),
                address_line=fake.street_address(),
                postal_code=fake.postcode(),
                city=fake.city(),
                bsn=str(random.randint(100000000, 999999999)),
                iban=fake.iban(),
                notes=fake.sentence(),
            )

            EmployeeProfile.objects.create(
                person=person,
                hired_date=fake.date_between(start_date="-5y", end_date="today"),
                job_title=random.choice(["Developer", "Trainer", "Jobcoach"]),
            )

    # ------------------------------------------------
    # SIGNALS
    # ------------------------------------------------

    def _seed_signals(self, people, categories, created_by, assignees, per_person_avg=2):
        for p in people:
            count = max(0, int(random.gauss(per_person_avg, 1)))

            for _ in range(count):
                Signal.objects.create(
                    person=p,
                    category=random.choice(categories),
                    title=fake.sentence(nb_words=5)[:150],
                    body=fake.paragraph(),
                    active_from=fake.date_time_between(
                        start_date="-30d",
                        end_date="+30d",
                        tzinfo=timezone.get_current_timezone(),
                    ),
                    assigned_to=random.choice(assignees),
                    created_by=created_by,
                    status=random.choice(["open", "done", "snoozed"]),
                    notify=random.choice([True, False]),
                )
