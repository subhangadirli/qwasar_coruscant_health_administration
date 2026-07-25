from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import PatientDoctorAssignment, Role
from apps.orders.models import OrderResult, ServiceOrder
from apps.records.models import HealthReading, Report

User = get_user_model()


class SmokeTests(TestCase):
    def test_health_check_ok(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_home_renders(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Coruscant Health Administration")


class RoleDashboardTests(TestCase):
    """Every role dashboard must render.

    These pages are mostly links, which is exactly what a broken or renamed
    url name breaks first, and only at render time.
    """

    def dashboard_for(self, role, is_approved=True):
        user = User.objects.create_user(
            username=f"{role}-user",
            password="pw",
            role=role,
            is_approved=is_approved,
        )
        self.client.force_login(user)
        return self.client.get(reverse("dashboard:home"))

    def test_each_role_dashboard_renders(self):
        for role in Role.values:
            with self.subTest(role=role):
                self.assertEqual(self.dashboard_for(role).status_code, 200)

    def test_the_doctor_dashboard_links_to_the_caseload(self):
        response = self.dashboard_for(Role.DOCTOR)
        self.assertContains(response, reverse("records:patients"))
        self.assertContains(response, reverse("records:doctor_reports"))
        self.assertContains(response, reverse("orders:doctor_orders"))

    def test_an_unapproved_user_is_sent_to_pending(self):
        response = self.dashboard_for(Role.DOCTOR, is_approved=False)
        self.assertRedirects(response, reverse("accounts:pending"))


class SeedDemoCommandTests(TestCase):
    def test_seed_demo_creates_a_coherent_dataset(self):
        call_command("seed_demo", verbosity=0)
        self.assertEqual(User.objects.count(), 8)
        self.assertEqual(PatientDoctorAssignment.objects.count(), 2)
        self.assertEqual(HealthReading.objects.count(), 14)
        self.assertEqual(Report.objects.published().count(), 1)
        self.assertEqual(ServiceOrder.objects.count(), 2)
        self.assertEqual(OrderResult.objects.count(), 1)
        # Pending accounts exist so the approval queue has something to show.
        self.assertTrue(User.objects.filter(is_approved=False).exists())

    def test_seed_demo_is_idempotent(self):
        call_command("seed_demo", verbosity=0)
        call_command("seed_demo", verbosity=0)
        self.assertEqual(User.objects.count(), 8)
        self.assertEqual(HealthReading.objects.count(), 14)
        self.assertEqual(ServiceOrder.objects.count(), 2)

    def test_seeded_accounts_can_log_in(self):
        call_command("seed_demo", verbosity=0)
        self.assertTrue(self.client.login(username="dr.kenobi", password="demopass123"))
