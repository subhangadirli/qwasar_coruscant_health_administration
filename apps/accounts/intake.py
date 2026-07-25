"""Provisioning for emergency fast-intake.

Kept apart from the view so the creation of an account is one small,
transactional, testable unit: the emergency desk types a name, and a real
approved patient record exists a moment later.
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.crypto import get_random_string
from django.utils.text import slugify

from .models import EmergencyIntake, Role

User = get_user_model()


def _unique_username(full_name):
    """A readable, collision-free username derived from the patient's name."""
    base = slugify(full_name) or "patient"
    while True:
        username = f"{base}-{get_random_string(6).lower()}"
        if not User.objects.filter(username=username).exists():
            return username


@transaction.atomic
def admit_emergency_patient(full_name, admitted_by, presenting_complaint=""):
    """Create an approved patient and record the emergency admission.

    The account is approved on creation so it never waits in the admin queue,
    and it is given no usable password yet: the goal here is a record a
    clinician can attach readings and orders to immediately. Issuing login
    credentials is a deliberate, separate step.
    """
    first_name, _, last_name = full_name.strip().partition(" ")
    patient = User(
        username=_unique_username(full_name),
        role=Role.PATIENT,
        is_approved=True,
        first_name=first_name,
        last_name=last_name,
    )
    patient.set_unusable_password()
    patient.save()
    return EmergencyIntake.objects.create(
        patient=patient,
        admitted_by=admitted_by,
        presenting_complaint=presenting_complaint,
    )
