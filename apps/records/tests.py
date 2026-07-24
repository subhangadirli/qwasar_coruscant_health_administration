import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
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


class ReadingChartDataTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="pat", password="pw", role=Role.PATIENT, is_approved=True
        )
        self.url = reverse("records:readings")
        self.client.force_login(self.patient)

    def chart(self, **params):
        return self.client.get(self.url, params).context["chart_data"]

    def test_no_chart_without_readings(self):
        self.assertIsNone(self.chart())

    def test_points_run_oldest_to_newest(self):
        now = timezone.now()
        make_reading(self.patient, value=Decimal("60"), recorded_at=now - timedelta(days=3))
        make_reading(self.patient, value=Decimal("70"), recorded_at=now - timedelta(days=2))
        make_reading(self.patient, value=Decimal("80"), recorded_at=now - timedelta(days=1))

        self.assertEqual(self.chart()["values"], [60.0, 70.0, 80.0])

    def test_chart_follows_the_selected_metric(self):
        make_reading(self.patient, metric=MetricType.HEART_RATE, value=Decimal("70"))
        make_reading(self.patient, metric=MetricType.WEIGHT, value=Decimal("81.5"))

        chart = self.chart(metric=MetricType.WEIGHT)

        self.assertEqual(chart["metric"], MetricType.WEIGHT)
        self.assertEqual(chart["values"], [81.5])
        self.assertEqual(chart["unit"], DEFAULT_UNITS[MetricType.WEIGHT])

    def test_defaults_to_the_most_recently_recorded_metric(self):
        now = timezone.now()
        make_reading(
            self.patient, metric=MetricType.HEART_RATE, recorded_at=now - timedelta(days=5)
        )
        make_reading(
            self.patient, metric=MetricType.WEIGHT, recorded_at=now - timedelta(hours=1)
        )

        self.assertEqual(self.chart()["metric"], MetricType.WEIGHT)

    def test_no_chart_when_selected_metric_has_no_readings(self):
        make_reading(self.patient, metric=MetricType.HEART_RATE)
        self.assertIsNone(self.chart(metric=MetricType.SPO2))

    def test_chart_excludes_other_patients_readings(self):
        other = User.objects.create_user(
            username="other", password="pw", role=Role.PATIENT, is_approved=True
        )
        make_reading(other, value=Decimal("123"))
        make_reading(self.patient, value=Decimal("70"))

        self.assertEqual(self.chart()["values"], [70.0])

    def test_point_count_is_capped(self):
        now = timezone.now()
        for minutes in range(105):
            make_reading(self.patient, recorded_at=now - timedelta(minutes=minutes + 1))

        chart = self.chart()

        self.assertEqual(len(chart["values"]), 100)
        self.assertEqual(len(chart["labels"]), 100)

    def test_chart_payload_is_json_serializable(self):
        make_reading(self.patient)
        json.dumps(self.chart())


class AddReadingViewTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="pat", password="pw", role=Role.PATIENT, is_approved=True
        )
        self.url = reverse("records:add_reading")
        self.client.force_login(self.patient)

    def payload(self, **overrides):
        recorded = timezone.now() - timedelta(hours=2)
        data = {
            "metric": MetricType.HEART_RATE,
            "value": "72",
            "unit": "",
            "recorded_at": recorded.strftime("%Y-%m-%dT%H:%M"),
        }
        return {**data, **overrides}

    def test_manual_entry_creates_reading_for_the_logged_in_patient(self):
        response = self.client.post(self.url, self.payload())
        self.assertRedirects(response, reverse("records:readings"))
        reading = HealthReading.objects.get()
        self.assertEqual(reading.patient, self.patient)
        self.assertEqual(reading.source, ReadingSource.MANUAL)
        self.assertEqual(reading.unit, DEFAULT_UNITS[MetricType.HEART_RATE])

    def test_patient_field_in_post_data_is_ignored(self):
        victim = User.objects.create_user(
            username="victim", password="pw", role=Role.PATIENT, is_approved=True
        )
        self.client.post(self.url, self.payload(patient=victim.pk))
        self.assertEqual(HealthReading.objects.get().patient, self.patient)

    def test_future_reading_is_rejected(self):
        future = timezone.now() + timedelta(days=1)
        response = self.client.post(
            self.url, self.payload(recorded_at=future.strftime("%Y-%m-%dT%H:%M"))
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(HealthReading.objects.exists())

    def test_doctor_cannot_add_readings(self):
        doctor = User.objects.create_user(
            username="doc", password="pw", role=Role.DOCTOR, is_approved=True
        )
        self.client.force_login(doctor)
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 403)


class ReadingCSVUploadTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="pat", password="pw", role=Role.PATIENT, is_approved=True
        )
        self.url = reverse("records:upload_readings")
        self.client.force_login(self.patient)

    def upload(self, text, name="readings.csv"):
        return self.client.post(
            self.url,
            {"csv_file": SimpleUploadedFile(name, text.encode("utf-8"), "text/csv")},
        )

    def test_valid_csv_imports_every_row(self):
        response = self.upload(
            "metric,value,unit,recorded_at\n"
            "heart_rate,72,bpm,2026-07-20T08:30:00\n"
            "weight,70.5,kg,2026-07-20T08:31:00\n"
        )
        self.assertRedirects(response, reverse("records:readings"))
        self.assertEqual(HealthReading.objects.count(), 2)
        self.assertTrue(
            all(
                r.patient == self.patient and r.source == ReadingSource.CSV
                for r in HealthReading.objects.all()
            )
        )

    def test_unit_column_is_optional(self):
        self.upload(
            "metric,value,recorded_at\nheart_rate,72,2026-07-20T08:30:00\n"
        )
        self.assertEqual(
            HealthReading.objects.get().unit, DEFAULT_UNITS[MetricType.HEART_RATE]
        )

    def test_missing_required_column_is_rejected(self):
        response = self.upload("metric,value\nheart_rate,72\n")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(HealthReading.objects.exists())
        self.assertContains(response, "recorded_at")

    def test_one_bad_row_rejects_the_whole_file(self):
        response = self.upload(
            "metric,value,recorded_at\n"
            "heart_rate,72,2026-07-20T08:30:00\n"
            "heart_rate,not-a-number,2026-07-20T08:31:00\n"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(HealthReading.objects.exists())

    def test_unknown_metric_is_rejected(self):
        response = self.upload(
            "metric,value,recorded_at\nblood_pressure,120,2026-07-20T08:30:00\n"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(HealthReading.objects.exists())

    def test_future_row_is_rejected(self):
        future = (timezone.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
        response = self.upload(f"metric,value,recorded_at\nheart_rate,72,{future}\n")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(HealthReading.objects.exists())

    def test_negative_value_is_rejected(self):
        response = self.upload(
            "metric,value,recorded_at\nheart_rate,-5,2026-07-20T08:30:00\n"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(HealthReading.objects.exists())

    def test_non_finite_value_is_rejected(self):
        response = self.upload(
            "metric,value,recorded_at\nheart_rate,NaN,2026-07-20T08:30:00\n"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(HealthReading.objects.exists())

    def test_header_only_file_is_rejected(self):
        response = self.upload("metric,value,recorded_at\n")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(HealthReading.objects.exists())

    def test_non_utf8_file_is_rejected(self):
        response = self.client.post(
            self.url,
            {
                "csv_file": SimpleUploadedFile(
                    "readings.csv", b"\xff\xfe\x00binary", "text/csv"
                )
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(HealthReading.objects.exists())

    def test_doctor_cannot_upload(self):
        doctor = User.objects.create_user(
            username="doc", password="pw", role=Role.DOCTOR, is_approved=True
        )
        self.client.force_login(doctor)
        response = self.upload(
            "metric,value,recorded_at\nheart_rate,72,2026-07-20T08:30:00\n"
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(HealthReading.objects.exists())
