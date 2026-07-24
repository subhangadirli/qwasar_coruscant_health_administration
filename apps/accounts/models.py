from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    PATIENT = "patient", "Patient"
    DOCTOR = "doctor", "Doctor"
    DEPARTMENT = "department", "Department / Service"
    ADMIN = "admin", "Administrator"
    EMERGENCY = "emergency", "Emergency Services"


class User(AbstractUser):
    """Custom user with a role and an admin-approval gate.

    Patients and doctors self-register but stay unapproved (``is_approved``
    False) until an administrator acknowledges them.
    """

    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.PATIENT
    )
    is_approved = models.BooleanField(
        default=False,
        help_text="Set by an administrator to activate the account.",
    )
    is_rejected = models.BooleanField(
        default=False,
        help_text=(
            "Set by an administrator to decline the registration. Kept as a "
            "record instead of deleting the account."
        ),
    )

    @property
    def is_patient(self):
        return self.role == Role.PATIENT

    @property
    def is_doctor(self):
        return self.role == Role.DOCTOR

    @property
    def is_department(self):
        return self.role == Role.DEPARTMENT

    @property
    def is_emergency(self):
        return self.role == Role.EMERGENCY

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
