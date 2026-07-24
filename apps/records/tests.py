from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role

from .models import DEFAULT_UNITS, HealthReading, MetricType, ReadingSource

User = get_user_model()


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
