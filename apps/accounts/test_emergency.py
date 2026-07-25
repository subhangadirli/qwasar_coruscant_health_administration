from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .intake import admit_emergency_patient
from .models import EmergencyIntake, Role

User = get_user_model()


def make_user(username, role, **extra):
    return User.objects.create_user(
        username=username,
        password="pw",
        role=role,
        is_approved=extra.pop("is_approved", True),
        **extra,
    )


class AdmitEmergencyPatientTests(TestCase):
    """The provisioning helper, exercised directly."""

    def setUp(self):
        self.desk = make_user("er", Role.EMERGENCY)

    def test_creates_an_approved_patient_record(self):
        intake, _ = admit_emergency_patient("Jane Roe", self.desk)
        patient = intake.patient
        self.assertEqual(patient.role, Role.PATIENT)
        self.assertTrue(patient.is_approved)
        self.assertFalse(patient.is_rejected)

    def test_splits_the_name_and_records_the_admitter(self):
        intake, _ = admit_emergency_patient(
            "Jane Roe", self.desk, presenting_complaint="Chest pain"
        )
        self.assertEqual(intake.patient.first_name, "Jane")
        self.assertEqual(intake.patient.last_name, "Roe")
        self.assertEqual(intake.admitted_by, self.desk)
        self.assertEqual(intake.presenting_complaint, "Chest pain")

    def test_returns_a_usable_password(self):
        intake, raw_password = admit_emergency_patient("Jane Roe", self.desk)
        self.assertTrue(intake.patient.has_usable_password())
        self.assertTrue(intake.patient.check_password(raw_password))

    def test_repeated_names_get_distinct_usernames(self):
        first, _ = admit_emergency_patient("Jane Roe", self.desk)
        second, _ = admit_emergency_patient("Jane Roe", self.desk)
        self.assertNotEqual(first.patient.username, second.patient.username)

    def test_an_unnamed_patient_still_gets_a_record(self):
        intake, _ = admit_emergency_patient("   ", self.desk)
        self.assertTrue(intake.patient.username.startswith("patient-"))


class EmergencyIntakeAccessTests(TestCase):
    def setUp(self):
        self.url = reverse("accounts:emergency_intake")

    def test_an_emergency_account_can_open_intake(self):
        self.client.force_login(make_user("er", Role.EMERGENCY))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_a_patient_cannot_open_intake(self):
        self.client.force_login(make_user("pat", Role.PATIENT))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_a_doctor_cannot_open_intake(self):
        self.client.force_login(make_user("doc", Role.DOCTOR))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_an_unapproved_emergency_account_is_sent_to_pending(self):
        self.client.force_login(
            make_user("newer", Role.EMERGENCY, is_approved=False)
        )
        self.assertRedirects(
            self.client.get(self.url), reverse("accounts:pending")
        )

    def test_anonymous_users_are_sent_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)


class EmergencyIntakeViewTests(TestCase):
    def setUp(self):
        self.desk = make_user("er", Role.EMERGENCY)
        self.url = reverse("accounts:emergency_intake")
        self.client.force_login(self.desk)

    def submit(self, **data):
        data.setdefault("full_name", "Jane Roe")
        return self.client.post(self.url, data)

    def test_submitting_admits_a_patient(self):
        response = self.submit(presenting_complaint="Chest pain")
        self.assertEqual(response.status_code, 200)
        intake = EmergencyIntake.objects.get()
        self.assertEqual(response.context["admitted"], intake)
        self.assertEqual(intake.admitted_by, self.desk)

    def test_the_temporary_password_is_shown_once(self):
        response = self.submit()
        raw_password = response.context["raw_password"]
        self.assertContains(response, raw_password)
        # The provisioned account really accepts that credential.
        patient = EmergencyIntake.objects.get().patient
        self.assertTrue(patient.check_password(raw_password))

    def test_an_admitted_patient_skips_the_admin_approval_queue(self):
        self.submit()
        admin = make_user("boss", Role.ADMIN)
        self.client.force_login(admin)
        response = self.client.get(reverse("accounts:approvals"))
        self.assertEqual(list(response.context["pending_users"]), [])

    def test_a_blank_name_is_rejected(self):
        response = self.client.post(self.url, {"full_name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(EmergencyIntake.objects.exists())

    def test_recent_admissions_are_scoped_to_this_desk(self):
        self.submit(full_name="Mine One")
        other_desk = make_user("er2", Role.EMERGENCY)
        admit_emergency_patient("Their One", other_desk)
        response = self.client.get(self.url)
        recent = list(response.context["recent_intakes"])
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].admitted_by, self.desk)
