from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role

from .models import HealthReading, MetricType
from .trends import TrendDirection, TrendStatus, analyse, summarise_patient

User = get_user_model()


class TrendAnalysisTests(TestCase):
    """The readings are built newest-last and reversed, so a test reads in
    chronological order: `[oldest, ..., newest]`."""

    def setUp(self):
        self.patient = User.objects.create_user(
            username="pat", password="pw", role=Role.PATIENT, is_approved=True
        )

    def make(self, metric, values, unit=""):
        """Create readings a minute apart and return them newest first."""
        start = timezone.now() - timedelta(hours=len(values))
        for offset, value in enumerate(values):
            HealthReading.objects.create(
                patient=self.patient,
                metric=metric,
                value=Decimal(str(value)),
                unit=unit,
                recorded_at=start + timedelta(minutes=offset),
            )
        return list(self.patient.health_readings.filter(metric=metric))

    def test_too_few_readings_is_insufficient(self):
        readings = self.make(MetricType.HEART_RATE, [70, 72, 74])
        trend = analyse(readings)
        self.assertEqual(trend.status, TrendStatus.INSUFFICIENT)
        self.assertEqual(trend.sample_size, 3)
        self.assertIsNone(trend.change)
        self.assertFalse(trend.is_comparable)

    def test_falling_toward_the_range_is_improving(self):
        readings = self.make(MetricType.HEART_RATE, [130, 128, 126, 99, 98, 97])
        trend = analyse(readings)
        self.assertEqual(trend.status, TrendStatus.IMPROVING)
        self.assertEqual(trend.direction, TrendDirection.DOWN)
        self.assertEqual(trend.baseline_mean, Decimal("128.00"))
        self.assertEqual(trend.recent_mean, Decimal("98.00"))
        self.assertEqual(trend.change, Decimal("-30.00"))

    def test_rising_toward_the_range_is_also_improving(self):
        # Below the healthy band, so climbing is the good direction. Raw
        # direction alone would have called this the opposite.
        readings = self.make(MetricType.HEART_RATE, [42, 44, 46, 58, 59, 60])
        trend = analyse(readings)
        self.assertEqual(trend.status, TrendStatus.IMPROVING)
        self.assertEqual(trend.direction, TrendDirection.UP)

    def test_moving_away_from_the_range_is_worsening(self):
        readings = self.make(MetricType.BP_SYSTOLIC, [118, 119, 120, 150, 152, 154])
        trend = analyse(readings)
        self.assertEqual(trend.status, TrendStatus.WORSENING)
        self.assertEqual(trend.direction, TrendDirection.UP)

    def test_movement_inside_the_range_is_stable(self):
        readings = self.make(MetricType.SPO2, [96, 96, 96, 99, 99, 99])
        trend = analyse(readings)
        self.assertEqual(trend.status, TrendStatus.STABLE)
        self.assertEqual(trend.direction, TrendDirection.UP)

    def test_movement_below_the_noise_floor_is_stable(self):
        # Heart rate's band is 40 wide, so anything under 2 bpm of drift is
        # not treated as a change.
        readings = self.make(MetricType.HEART_RATE, [110, 110, 110, 109, 109, 109])
        trend = analyse(readings)
        self.assertEqual(trend.status, TrendStatus.STABLE)
        self.assertEqual(trend.direction, TrendDirection.DOWN)

    def test_metric_without_a_reference_range_is_unclear(self):
        readings = self.make(MetricType.WEIGHT, [90, 89, 88, 82, 81, 80])
        trend = analyse(readings)
        self.assertEqual(trend.status, TrendStatus.UNCLEAR)
        self.assertEqual(trend.direction, TrendDirection.DOWN)
        self.assertEqual(trend.change, Decimal("-8.00"))

    def test_identical_windows_are_level_and_stable(self):
        readings = self.make(MetricType.HEART_RATE, [70, 70, 70, 70])
        trend = analyse(readings)
        self.assertEqual(trend.direction, TrendDirection.FLAT)
        self.assertEqual(trend.status, TrendStatus.STABLE)
        self.assertEqual(trend.change, Decimal("0.00"))

    def test_windows_are_equal_sized_when_history_is_short(self):
        readings = self.make(MetricType.HEART_RATE, [70, 72, 74, 76, 78, 80])
        self.assertEqual(analyse(readings).sample_size, 6)

    def test_windows_are_capped_by_the_window_size(self):
        readings = self.make(MetricType.HEART_RATE, list(range(60, 90)))
        self.assertEqual(analyse(readings).sample_size, 10)

    def test_an_odd_reading_is_dropped_rather_than_unbalancing_windows(self):
        readings = self.make(MetricType.HEART_RATE, [70, 72, 74, 76, 78])
        self.assertEqual(analyse(readings).sample_size, 4)

    def test_labels_are_human_readable(self):
        readings = self.make(MetricType.HEART_RATE, [130, 128, 126, 99, 98, 97])
        trend = analyse(readings)
        self.assertEqual(trend.label, "Heart rate")
        self.assertEqual(trend.status_label, "Improving")
        self.assertEqual(trend.direction_label, "Falling")

    def test_unit_is_carried_from_the_readings(self):
        readings = self.make(MetricType.HEART_RATE, [70, 71, 72, 73], unit="bpm")
        self.assertEqual(analyse(readings).unit, "bpm")


class SummarisePatientTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="pat", password="pw", role=Role.PATIENT, is_approved=True
        )

    def add(self, patient, metric, values):
        start = timezone.now() - timedelta(hours=len(values))
        for offset, value in enumerate(values):
            HealthReading.objects.create(
                patient=patient,
                metric=metric,
                value=Decimal(str(value)),
                recorded_at=start + timedelta(minutes=offset),
            )

    def test_only_metrics_with_readings_are_summarised(self):
        self.add(self.patient, MetricType.HEART_RATE, [70, 72, 74, 76])
        trends = summarise_patient(self.patient)
        self.assertEqual([t.metric for t in trends], [MetricType.HEART_RATE])

    def test_metrics_keep_their_declared_order(self):
        self.add(self.patient, MetricType.WEIGHT, [80, 81, 82, 83])
        self.add(self.patient, MetricType.HEART_RATE, [70, 72, 74, 76])
        trends = summarise_patient(self.patient)
        self.assertEqual(
            [t.metric for t in trends],
            [MetricType.HEART_RATE, MetricType.WEIGHT],
        )

    def test_a_patient_with_no_readings_has_no_trends(self):
        self.assertEqual(summarise_patient(self.patient), [])

    def test_another_patients_readings_are_not_mixed_in(self):
        other = User.objects.create_user(
            username="other", password="pw", role=Role.PATIENT, is_approved=True
        )
        self.add(other, MetricType.HEART_RATE, [130, 128, 126, 124])
        self.add(self.patient, MetricType.HEART_RATE, [70, 71, 72, 73])
        trend = summarise_patient(self.patient)[0]
        self.assertEqual(trend.recent_mean, Decimal("72.50"))
