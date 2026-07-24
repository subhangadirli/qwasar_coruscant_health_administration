from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import PatientDoctorAssignment, Role

from .models import HealthReading, MetricType, Report, ReportKind, ReportStatus

User = get_user_model()


def make_user(username, role, **extra):
    return User.objects.create_user(
        username=username,
        password="pw",
        role=role,
        is_approved=extra.pop("is_approved", True),
        **extra,
    )


def add_readings(patient, metric, values):
    start = timezone.now() - timedelta(hours=len(values))
    for offset, value in enumerate(values):
        HealthReading.objects.create(
            patient=patient,
            metric=metric,
            value=Decimal(str(value)),
            recorded_at=start + timedelta(minutes=offset),
        )


class DoctorPatientListTests(TestCase):
    def setUp(self):
        self.doctor = make_user("doc", Role.DOCTOR)
        self.patient = make_user("pat", Role.PATIENT)
        self.url = reverse("records:patients")
        self.client.force_login(self.doctor)

    def assign(self, **overrides):
        fields = {"doctor": self.doctor, "patient": self.patient, **overrides}
        return PatientDoctorAssignment.objects.create(**fields)

    def patients(self, response):
        return list(response.context["patients"])

    def test_assigned_patient_is_listed(self):
        self.assign()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.patients(response), [self.patient])

    def test_unassigned_patient_is_not_listed(self):
        response = self.client.get(self.url)
        self.assertEqual(self.patients(response), [])
        self.assertContains(response, "No patients assigned")

    def test_ended_assignment_is_not_listed(self):
        self.assign(is_active=False)
        self.assertEqual(self.patients(self.client.get(self.url)), [])

    def test_another_doctors_patient_is_not_listed(self):
        other_doctor = make_user("doc2", Role.DOCTOR)
        PatientDoctorAssignment.objects.create(
            doctor=other_doctor, patient=self.patient
        )
        self.assertEqual(self.patients(self.client.get(self.url)), [])

    def test_reading_counts_are_annotated(self):
        self.assign()
        add_readings(self.patient, MetricType.HEART_RATE, [70, 72])
        listed = self.patients(self.client.get(self.url))[0]
        self.assertEqual(listed.reading_count, 2)
        self.assertIsNotNone(listed.last_reading_at)

    def test_a_patient_without_readings_counts_zero(self):
        self.assign()
        listed = self.patients(self.client.get(self.url))[0]
        self.assertEqual(listed.reading_count, 0)
        self.assertIsNone(listed.last_reading_at)

    def test_patient_role_is_forbidden(self):
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_department_role_is_forbidden(self):
        self.client.force_login(make_user("dept", Role.DEPARTMENT))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_unapproved_doctor_is_sent_to_pending(self):
        self.client.force_login(make_user("newdoc", Role.DOCTOR, is_approved=False))
        self.assertRedirects(
            self.client.get(self.url), reverse("accounts:pending")
        )

    def test_anonymous_is_sent_to_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])


class DoctorPatientDetailTests(TestCase):
    def setUp(self):
        self.doctor = make_user("doc", Role.DOCTOR)
        self.patient = make_user("pat", Role.PATIENT)
        self.assignment = PatientDoctorAssignment.objects.create(
            doctor=self.doctor, patient=self.patient
        )
        self.url = reverse("records:patient_detail", args=[self.patient.pk])
        self.client.force_login(self.doctor)

    def test_assigned_patient_record_opens(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["patient"], self.patient)

    def test_unassigned_patient_is_not_found(self):
        stranger = make_user("stranger", Role.PATIENT)
        url = reverse("records:patient_detail", args=[stranger.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_ended_assignment_is_not_found(self):
        self.assignment.is_active = False
        self.assignment.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_unapproved_patient_is_not_found(self):
        self.patient.is_approved = False
        self.patient.save(update_fields=["is_approved"])
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_another_patient_cannot_read_the_record(self):
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_trends_are_summarised(self):
        add_readings(self.patient, MetricType.HEART_RATE, [130, 128, 126, 99, 98, 97])
        trends = self.client.get(self.url).context["trends"]
        self.assertEqual([t.metric for t in trends], [MetricType.HEART_RATE])
        self.assertEqual(trends[0].status, "improving")

    def test_chart_defaults_to_the_latest_metric(self):
        add_readings(self.patient, MetricType.HEART_RATE, [70, 72])
        add_readings(self.patient, MetricType.WEIGHT, [80, 81])
        chart = self.client.get(self.url).context["chart_data"]
        self.assertEqual(chart["metric"], MetricType.WEIGHT)

    def test_metric_filter_narrows_readings_and_chart(self):
        add_readings(self.patient, MetricType.HEART_RATE, [70, 72])
        add_readings(self.patient, MetricType.WEIGHT, [80, 81])
        response = self.client.get(self.url, {"metric": MetricType.HEART_RATE})
        self.assertEqual(
            {r.metric for r in response.context["readings"]},
            {MetricType.HEART_RATE},
        )
        self.assertEqual(
            response.context["chart_data"]["metric"], MetricType.HEART_RATE
        )

    def test_unknown_metric_filter_is_ignored(self):
        add_readings(self.patient, MetricType.HEART_RATE, [70, 72])
        response = self.client.get(self.url, {"metric": "telepathy"})
        self.assertIsNone(response.context["selected_metric"])
        self.assertEqual(len(response.context["readings"]), 2)

    def test_no_readings_yields_no_chart_and_no_trends(self):
        response = self.client.get(self.url)
        self.assertIsNone(response.context["chart_data"])
        self.assertEqual(response.context["trends"], [])

    def test_another_patients_readings_are_not_shown(self):
        other = make_user("other", Role.PATIENT)
        add_readings(other, MetricType.HEART_RATE, [200, 201])
        add_readings(self.patient, MetricType.HEART_RATE, [70])
        readings = self.client.get(self.url).context["readings"]
        self.assertEqual([r.patient for r in readings], [self.patient])


class DoctorPatientReportVisibilityTests(TestCase):
    def setUp(self):
        self.doctor = make_user("doc", Role.DOCTOR)
        self.other_doctor = make_user("doc2", Role.DOCTOR)
        self.patient = make_user("pat", Role.PATIENT)
        PatientDoctorAssignment.objects.create(
            doctor=self.doctor, patient=self.patient
        )
        self.url = reverse("records:patient_detail", args=[self.patient.pk])
        self.client.force_login(self.doctor)

    def report(self, doctor, status, title="Note"):
        return Report.objects.create(
            patient=self.patient,
            doctor=doctor,
            kind=ReportKind.REPORT,
            title=title,
            body="body",
            status=status,
        )

    def reports(self):
        return list(self.client.get(self.url).context["reports"])

    def test_published_report_from_any_doctor_is_visible(self):
        report = self.report(self.other_doctor, ReportStatus.PUBLISHED)
        self.assertEqual(self.reports(), [report])

    def test_own_draft_is_visible(self):
        report = self.report(self.doctor, ReportStatus.DRAFT)
        self.assertEqual(self.reports(), [report])

    def test_another_doctors_draft_is_hidden(self):
        self.report(self.other_doctor, ReportStatus.DRAFT)
        self.assertEqual(self.reports(), [])
