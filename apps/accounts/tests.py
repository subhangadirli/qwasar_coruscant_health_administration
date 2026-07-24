from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Role

User = get_user_model()


class RegistrationTests(TestCase):
    def test_register_creates_unapproved_user(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "patient1",
                "email": "p1@example.com",
                "role": Role.PATIENT.value,
                "password1": "s3cure-pass-42",
                "password2": "s3cure-pass-42",
            },
        )
        self.assertRedirects(response, reverse("accounts:register_done"))
        user = User.objects.get(username="patient1")
        self.assertEqual(user.role, Role.PATIENT)
        self.assertFalse(user.is_approved)

    def test_cannot_self_register_as_admin(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "sneaky",
                "email": "s@example.com",
                "role": Role.ADMIN.value,
                "password1": "s3cure-pass-42",
                "password2": "s3cure-pass-42",
            },
        )
        self.assertEqual(response.status_code, 200)  # re-rendered with error
        self.assertFalse(User.objects.filter(username="sneaky").exists())


class ApprovalGateTests(TestCase):
    def setUp(self):
        self.unapproved = User.objects.create_user(
            username="waiting", password="pw", role=Role.PATIENT
        )
        self.approved = User.objects.create_user(
            username="active", password="pw", role=Role.PATIENT, is_approved=True
        )

    def test_unapproved_user_redirected_to_pending(self):
        self.client.force_login(self.unapproved)
        response = self.client.get(reverse("dashboard:home"))
        self.assertRedirects(response, reverse("accounts:pending"))

    def test_approved_user_sees_role_dashboard(self):
        self.client.force_login(self.approved)
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Patient dashboard")


class ApprovalWorkflowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="boss", password="pw", role=Role.ADMIN, is_approved=True
        )
        self.pending_user = User.objects.create_user(
            username="newdoc", password="pw", role=Role.DOCTOR
        )

    def test_non_admin_cannot_view_approvals(self):
        patient = User.objects.create_user(
            username="p", password="pw", role=Role.PATIENT, is_approved=True
        )
        self.client.force_login(patient)
        response = self.client.get(reverse("accounts:approvals"))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_approve_user(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:approve", args=[self.pending_user.pk])
        )
        self.assertRedirects(response, reverse("accounts:approvals"))
        self.pending_user.refresh_from_db()
        self.assertTrue(self.pending_user.is_approved)

    def test_admin_can_reject_user(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:reject", args=[self.pending_user.pk])
        )
        self.assertRedirects(response, reverse("accounts:approvals"))
        self.assertFalse(User.objects.filter(pk=self.pending_user.pk).exists())
