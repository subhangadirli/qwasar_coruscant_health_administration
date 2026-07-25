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


# Long enough to resist guessing, short enough to read aloud at a desk.
_TEMP_PASSWORD_LENGTH = 12


@transaction.atomic
def admit_emergency_patient(full_name, admitted_by, presenting_complaint=""):
    """Provision an approved patient and record the emergency admission.

    Returns ``(intake, raw_password)``. The account is approved on creation so
    it never waits in the admin queue — the expedited path an emergency cannot
    wait on — and it is auto-provisioned with a generated password so it is a
    real, usable login without the desk inventing credentials. The raw password
    is returned to be shown once; only its hash is ever stored.
    """
    raw_password = get_random_string(_TEMP_PASSWORD_LENGTH)
    first_name, _, last_name = full_name.strip().partition(" ")
    patient = User.objects.create_user(
        username=_unique_username(full_name),
        password=raw_password,
        role=Role.PATIENT,
        is_approved=True,
        first_name=first_name,
        last_name=last_name,
    )
    intake = EmergencyIntake.objects.create(
        patient=patient,
        admitted_by=admitted_by,
        presenting_complaint=presenting_complaint,
    )
    return intake, raw_password
