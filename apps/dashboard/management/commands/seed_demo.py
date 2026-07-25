"""Populate the database with a coherent demo dataset.

Idempotent: every object is created via get_or_create keyed on a natural field,
so running it twice does not duplicate anything. Intended for a fresh demo or a
peer-review walkthrough — never for real patient data. Passwords are printed on
completion so a reviewer can log straight in.

    python manage.py seed_demo
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import PatientDoctorAssignment, Role, User
from apps.orders.models import Department, OrderResult, ServiceOrder
from apps.records.models import HealthReading, MetricType, Report, ReportStatus

# One shared password across the demo accounts, printed at the end.
DEMO_PASSWORD = "demopass123"

DEMO_USERS = [
    # username, role, first, last, approved, staff/super
    ("admin.demo", Role.ADMIN, "Demo", "Admin", True, True),
    ("dr.kenobi", Role.DOCTOR, "Obi-Wan", "Kenobi", True, False),
    ("dr.pending", Role.DOCTOR, "Quinlan", "Vos", False, False),
    ("padme", Role.PATIENT, "Padmé", "Amidala", True, False),
    ("anakin", Role.PATIENT, "Anakin", "Skywalker", True, False),
    ("pat.pending", Role.PATIENT, "Sabé", "Naberrie", False, False),
    ("radiology", Role.DEPARTMENT, "Radiology", "Desk", True, False),
    ("er.desk", Role.EMERGENCY, "Emergency", "Desk", True, False),
]


class Command(BaseCommand):
    help = "Create a coherent, idempotent demo dataset (users, readings, orders)."

    @transaction.atomic
    def handle(self, *args, **options):
        users = {row[0]: self._user(*row) for row in DEMO_USERS}

        doctor = users["dr.kenobi"]
        patient = users["padme"]
        anakin = users["anakin"]
        department = self._department()
        department.staff.add(users["radiology"])

        for p in (patient, anakin):
            PatientDoctorAssignment.objects.get_or_create(patient=p, doctor=doctor)

        self._readings(patient)
        self._reports(doctor, patient)
        self._orders(doctor, patient, anakin, department, users["radiology"])

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write("")
        self.stdout.write("Accounts (all share one password):")
        for username, role, *_ in DEMO_USERS:
            self.stdout.write(f"  {username:14} {role}")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING(f"  password: {DEMO_PASSWORD}"))

    def _user(self, username, role, first, last, approved, is_admin):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "role": role,
                "first_name": first,
                "last_name": last,
                "is_approved": approved,
                "is_staff": is_admin,
                "is_superuser": is_admin,
            },
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save(update_fields=["password"])
        return user

    def _department(self):
        dept, _ = Department.objects.get_or_create(
            name="Radiology",
            defaults={"kind": "ct", "is_active": True},
        )
        return dept

    def _readings(self, patient):
        # A week of daily heart-rate and SpO2 readings, trending gently.
        if HealthReading.objects.filter(patient=patient).exists():
            return
        now = timezone.now()
        for day in range(7):
            when = now - timedelta(days=6 - day)
            HealthReading.objects.create(
                patient=patient,
                metric=MetricType.HEART_RATE,
                value=Decimal(78 - day),
                recorded_at=when,
            )
            HealthReading.objects.create(
                patient=patient,
                metric=MetricType.SPO2,
                value=Decimal(95 + (day % 3)),
                recorded_at=when,
            )

    def _reports(self, doctor, patient):
        report, created = Report.objects.get_or_create(
            patient=patient,
            doctor=doctor,
            title="Initial consultation",
            defaults={
                "kind": "report",
                "body": "Vitals within range. Continue monitoring heart rate daily.",
            },
        )
        if created:
            report.publish()

        Report.objects.get_or_create(
            patient=patient,
            doctor=doctor,
            title="Iron supplement",
            defaults={
                "kind": "prescription",
                "body": "Ferrous sulfate 325mg once daily with food.",
                "status": ReportStatus.DRAFT,
            },
        )

    def _orders(self, doctor, patient, anakin, department, dept_staff):
        # A completed order (with a result) and an open one, so both the
        # department queue and the patient/doctor status views have content.
        done, created = ServiceOrder.objects.get_or_create(
            patient=patient,
            doctor=doctor,
            department=department,
            procedure="CT chest",
            defaults={"notes": "Rule out effusion.", "priority": "routine"},
        )
        if created:
            done.start()
            done.complete()
            OrderResult.objects.get_or_create(
                order=done,
                defaults={
                    "summary": "No abnormality detected.",
                    "uploaded_by": dept_staff,
                },
            )

        ServiceOrder.objects.get_or_create(
            patient=anakin,
            doctor=doctor,
            department=department,
            procedure="CT abdomen",
            defaults={"notes": "Persistent pain.", "priority": "urgent"},
        )
