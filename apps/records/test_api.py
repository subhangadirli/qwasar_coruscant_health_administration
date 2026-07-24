import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role

from .models import (
    DEFAULT_UNITS,
    DeviceToken,
    HealthReading,
    MetricType,
    ReadingSource,
)

User = get_user_model()


class DeviceTokenModelTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="pat", password="pw", role=Role.PATIENT, is_approved=True
        )

    def test_raw_key_is_not_stored(self):
        token, raw_key = DeviceToken.issue(self.patient)
        self.assertNotEqual(token.key_hash, raw_key)
        self.assertEqual(token.key_hash, DeviceToken.hash_key(raw_key))

    def test_authenticate_round_trips(self):
        token, raw_key = DeviceToken.issue(self.patient)
        self.assertEqual(DeviceToken.authenticate(raw_key), token)

    def test_authenticate_rejects_unknown_and_empty_keys(self):
        DeviceToken.issue(self.patient)
        self.assertIsNone(DeviceToken.authenticate("nope"))
        self.assertIsNone(DeviceToken.authenticate(""))
        self.assertIsNone(DeviceToken.authenticate(None))

    def test_reissuing_replaces_the_previous_token(self):
        _, first = DeviceToken.issue(self.patient)
        _, second = DeviceToken.issue(self.patient)
        self.assertIsNone(DeviceToken.authenticate(first))
        self.assertIsNotNone(DeviceToken.authenticate(second))
        self.assertEqual(
            DeviceToken.objects.filter(patient=self.patient).count(), 1
        )


class DeviceIngestAPITests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="pat", password="pw", role=Role.PATIENT, is_approved=True
        )
        self.token, self.raw_key = DeviceToken.issue(self.patient)
        self.url = reverse("records:api_readings")

    def post(self, payload, key="__default__"):
        key = self.raw_key if key == "__default__" else key
        extra = {"HTTP_AUTHORIZATION": f"Bearer {key}"} if key else {}
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            **extra,
        )

    def reading(self, **overrides):
        return {
            "metric": MetricType.HEART_RATE.value,
            "value": 72,
            "unit": "bpm",
            "recorded_at": "2026-07-20T08:30:00Z",
            **overrides,
        }

    def test_valid_batch_is_stored(self):
        response = self.post(
            {"readings": [self.reading(), self.reading(value=75)]}
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"created": 2})
        self.assertEqual(HealthReading.objects.count(), 2)
        self.assertTrue(
            all(
                r.patient == self.patient and r.source == ReadingSource.DEVICE
                for r in HealthReading.objects.all()
            )
        )

    def test_successful_post_records_token_use(self):
        self.assertIsNone(self.token.last_used_at)
        self.post({"readings": [self.reading()]})
        self.token.refresh_from_db()
        self.assertIsNotNone(self.token.last_used_at)

    def test_missing_token_is_unauthorized(self):
        response = self.post({"readings": [self.reading()]}, key=None)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], "Bearer")
        self.assertFalse(HealthReading.objects.exists())

    def test_wrong_token_is_unauthorized(self):
        response = self.post({"readings": [self.reading()]}, key="bogus-key")
        self.assertEqual(response.status_code, 401)
        self.assertFalse(HealthReading.objects.exists())

    def test_non_bearer_scheme_is_unauthorized(self):
        response = self.client.post(
            self.url,
            data=json.dumps({"readings": [self.reading()]}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.raw_key}",
        )
        self.assertEqual(response.status_code, 401)

    def test_unapproved_patient_is_forbidden(self):
        self.patient.is_approved = False
        self.patient.save(update_fields=["is_approved"])
        response = self.post({"readings": [self.reading()]})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(HealthReading.objects.exists())

    def test_rejected_patient_is_forbidden(self):
        self.patient.is_rejected = True
        self.patient.save(update_fields=["is_rejected"])
        response = self.post({"readings": [self.reading()]})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(HealthReading.objects.exists())

    def test_readings_land_on_the_tokens_owner_only(self):
        other = User.objects.create_user(
            username="other", password="pw", role=Role.PATIENT, is_approved=True
        )
        DeviceToken.issue(other)
        self.post({"readings": [self.reading()]})
        self.assertEqual(HealthReading.objects.get().patient, self.patient)
        self.assertFalse(other.health_readings.exists())

    def test_get_is_not_allowed(self):
        response = self.client.get(
            self.url, HTTP_AUTHORIZATION=f"Bearer {self.raw_key}"
        )
        self.assertEqual(response.status_code, 405)

    def test_malformed_json_is_rejected(self):
        response = self.client.post(
            self.url,
            data="{not json",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_readings_list_is_rejected(self):
        self.assertEqual(self.post({"data": []}).status_code, 400)
        self.assertEqual(self.post({"readings": {}}).status_code, 400)
        self.assertEqual(self.post([]).status_code, 400)

    def test_empty_batch_is_rejected(self):
        self.assertEqual(self.post({"readings": []}).status_code, 400)

    def test_oversized_batch_is_rejected(self):
        response = self.post({"readings": [self.reading()] * 501})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(HealthReading.objects.exists())

    def test_one_invalid_reading_rejects_the_whole_batch(self):
        response = self.post(
            {"readings": [self.reading(), self.reading(value="not-a-number")]}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("details", response.json())
        self.assertFalse(HealthReading.objects.exists())

    def test_unknown_metric_is_rejected(self):
        response = self.post({"readings": [self.reading(metric="telepathy")]})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(HealthReading.objects.exists())

    def test_future_reading_is_rejected(self):
        future = (timezone.now() + timedelta(days=1)).isoformat()
        response = self.post({"readings": [self.reading(recorded_at=future)]})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(HealthReading.objects.exists())

    def test_non_object_reading_is_rejected(self):
        response = self.post({"readings": ["heart_rate,72"]})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(HealthReading.objects.exists())

    def test_unit_defaults_when_omitted(self):
        payload = self.reading()
        del payload["unit"]
        self.post({"readings": [payload]})
        self.assertEqual(
            HealthReading.objects.get().unit,
            DEFAULT_UNITS[MetricType.HEART_RATE],
        )


class DeviceTokenViewTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            username="pat", password="pw", role=Role.PATIENT, is_approved=True
        )
        self.url = reverse("records:device_token")
        self.client.force_login(self.patient)

    def test_page_shows_no_token_initially(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["token"])

    def test_post_issues_a_token_shown_once(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        raw_key = response.context["raw_key"]
        self.assertContains(response, raw_key)
        self.assertEqual(DeviceToken.authenticate(raw_key).patient, self.patient)

    def test_raw_key_is_absent_on_a_later_get(self):
        self.client.post(self.url)
        response = self.client.get(self.url)
        self.assertIsNone(response.context.get("raw_key"))
        self.assertIsNotNone(response.context["token"])

    def test_doctor_is_forbidden(self):
        doctor = User.objects.create_user(
            username="doc", password="pw", role=Role.DOCTOR, is_approved=True
        )
        self.client.force_login(doctor)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url).status_code, 403)
