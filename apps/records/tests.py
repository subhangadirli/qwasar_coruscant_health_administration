from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role

from .models import DEFAULT_UNITS, HealthReading, MetricType, ReadingSource

User = get_user_model()


def make_reading(patient, **kwargs):
    defaults = {
        "patient": patient,
        "metric": MetricType.HEART_RATE,
        "value": Decimal("72"),
        "recorded_at": timezone.now() - timedelta(hours=1),
    }
    return HealthReading.objects.create(**{**defaults, **kwargs})


class HealthReadingModelTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="pat", password="pw", role=Role.PATIENT, is_approved=True
        )

    def make(self, **kwargs):
        defaults = {
            "patient": self.patient,
            "metric": MetricType.HEART_RATE,
            "value": Decimal("72"),
            "recorded_at": timezone.now() - timedelta(hours=1),
        }
        return HealthReading.objects.create(**{**defaults, **kwargs})

    def test_unit_defaults_from_metric(self):
        reading = self.make(metric=MetricType.BLOOD_GLUCOSE)
        self.assertEqual(reading.unit, DEFAULT_UNITS[MetricType.BLOOD_GLUCOSE])

    def test_explicit_unit_is_preserved(self):
        reading = self.make(metric=MetricType.WEIGHT, unit="lb")
        self.assertEqual(reading.unit, "lb")

    def test_future_reading_is_rejected(self):
        reading = HealthReading(
            patient=self.patient,
            metric=MetricType.HEART_RATE,
            value=Decimal("70"),
            recorded_at=timezone.now() + timedelta(days=1),
        )
        with self.assertRaises(ValidationError) as ctx:
            reading.full_clean()
        self.assertIn("recorded_at", ctx.exception.message_dict)

    def test_negative_value_is_rejected(self):
        reading = HealthReading(
            patient=self.patient,
            metric=MetricType.HEART_RATE,
            value=Decimal("-1"),
            recorded_at=timezone.now() - timedelta(hours=1),
        )
        with self.assertRaises(ValidationError) as ctx:
            reading.full_clean()
        self.assertIn("value", ctx.exception.message_dict)

    def test_default_source_is_manual(self):
        self.assertEqual(self.make().source, ReadingSource.MANUAL)

    def test_ordering_is_newest_first(self):
        now = timezone.now()
        older = self.make(recorded_at=now - timedelta(days=2))
        newer = self.make(recorded_at=now - timedelta(days=1))
        self.assertEqual(list(HealthReading.objects.all()), [newer, older])

    def test_readings_are_scoped_to_their_patient(self):
        other = User.objects.create_user(
            username="other", password="pw", role=Role.PATIENT, is_approved=True
        )
        mine = self.make()
        HealthReading.objects.create(
            patient=other,
            metric=MetricType.HEART_RATE,
            value=Decimal("88"),
            recorded_at=timezone.now() - timedelta(hours=2),
        )
        self.assertEqual(list(self.patient.health_readings.all()), [mine])


class PatientReadingsViewTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="pat", password="pw", role=Role.PATIENT, is_approved=True
        )
        self.url = reverse("records:readings")

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={self.url}")

    def test_unapproved_patient_is_redirected_to_pending(self):
        waiting = User.objects.create_user(
            username="waiting", password="pw", role=Role.PATIENT
        )
        self.client.force_login(waiting)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("accounts:pending"))

    def test_doctor_is_forbidden(self):
        doctor = User.objects.create_user(
            username="doc", password="pw", role=Role.DOCTOR, is_approved=True
        )
        self.client.force_login(doctor)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_patient_sees_only_their_own_readings(self):
        other = User.objects.create_user(
            username="other", password="pw", role=Role.PATIENT, is_approved=True
        )
        mine = make_reading(self.patient)
        theirs = make_reading(other, value=Decimal("99"))

        self.client.force_login(self.patient)
        readings = self.client.get(self.url).context["readings"]

        self.assertIn(mine, readings)
        self.assertNotIn(theirs, readings)

    def test_metric_filter_narrows_the_list(self):
        heart = make_reading(self.patient, metric=MetricType.HEART_RATE)
        weight = make_reading(self.patient, metric=MetricType.WEIGHT)

        self.client.force_login(self.patient)
        response = self.client.get(self.url, {"metric": MetricType.WEIGHT})

        self.assertEqual(list(response.context["readings"]), [weight])
        self.assertNotIn(heart, response.context["readings"])

    def test_unknown_metric_filter_is_ignored(self):
        reading = make_reading(self.patient)
        self.client.force_login(self.patient)
        response = self.client.get(self.url, {"metric": "not-a-metric"})
        self.assertEqual(list(response.context["readings"]), [reading])
        self.assertIsNone(response.context["selected_metric"])

    def test_empty_state_is_shown_without_readings(self):
        self.client.force_login(self.patient)
        self.assertContains(self.client.get(self.url), "No readings yet")
