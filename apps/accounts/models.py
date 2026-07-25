from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
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


class AssignmentQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class PatientDoctorAssignment(models.Model):
    """Links a patient to a doctor who may see their records.

    This is the authorization edge for every doctor-facing view: a doctor
    reads a patient's readings and writes their reports only through an
    active assignment. Ending care sets ``is_active`` False rather than
    deleting the row, so the fact that the relationship once existed stays
    on record.
    """

    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="doctor_assignments",
        limit_choices_to={"role": Role.PATIENT},
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="patient_assignments",
        limit_choices_to={"role": Role.DOCTOR},
    )
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=200, blank=True)

    objects = AssignmentQuerySet.as_manager()

    class Meta:
        ordering = ("-assigned_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "doctor"], name="unique_patient_doctor"
            ),
        ]

    def clean(self):
        errors = {}
        if self.patient_id and self.patient.role != Role.PATIENT:
            errors["patient"] = "Assigned user must have the patient role."
        if self.doctor_id and self.doctor.role != Role.DOCTOR:
            errors["doctor"] = "Assigned user must have the doctor role."
        if errors:
            raise ValidationError(errors)

    @classmethod
    def patients_of(cls, doctor):
        """Approved patients this doctor is actively assigned to."""
        return User.objects.filter(
            role=Role.PATIENT,
            is_approved=True,
            is_rejected=False,
            doctor_assignments__doctor=doctor,
            doctor_assignments__is_active=True,
        ).distinct()

    @classmethod
    def is_assigned(cls, doctor, patient):
        return cls.objects.active().filter(doctor=doctor, patient=patient).exists()

    def __str__(self):
        return f"{self.patient.username} to {self.doctor.username}"


class EmergencyIntake(models.Model):
    """A patient admitted through emergency fast-intake.

    Emergency accounts create these to get an incoming patient into the
    system in seconds. The patient is auto-provisioned and approved on the
    spot, skipping the admin approval queue an emergency cannot wait on, and
    this row records who admitted them and why.
    """

    patient = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="emergency_intake",
        limit_choices_to={"role": Role.PATIENT},
    )
    admitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        # The admission is part of the patient's record, so it outlives the
        # account of the clinician who entered it.
        on_delete=models.PROTECT,
        related_name="emergency_admissions",
        limit_choices_to={"role": Role.EMERGENCY},
    )
    presenting_complaint = models.TextField(
        blank=True, help_text="What the patient presented with, if known."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Emergency intake of {self.patient.username}"
