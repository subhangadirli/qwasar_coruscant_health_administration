from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import PatientDoctorAssignment, Role

from .models import (
    Department,
    DepartmentKind,
    OrderPriority,
    OrderStatus,
    ServiceOrder,
)

User = get_user_model()


def make_user(username, role, **extra):
    return User.objects.create_user(
        username=username,
        password="pw",
        role=role,
        is_approved=extra.pop("is_approved", True),
        **extra,
    )


class OrderViewTestCase(TestCase):
    def setUp(self):
        self.doctor = make_user("doc", Role.DOCTOR)
        self.other_doctor = make_user("doc2", Role.DOCTOR)
        self.patient = make_user("pat", Role.PATIENT)
        self.department = Department.objects.create(
            name="Imaging", kind=DepartmentKind.CT
        )
        PatientDoctorAssignment.objects.create(
            doctor=self.doctor, patient=self.patient
        )
        self.client.force_login(self.doctor)

    def order(self, **overrides):
        fields = {
            "patient": self.patient,
            "doctor": self.doctor,
            "department": self.department,
            "procedure": "CT head without contrast",
            **overrides,
        }
        return ServiceOrder.objects.create(**fields)


class PlaceOrderTests(OrderViewTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("orders:place_order", args=[self.patient.pk])

    def payload(self, **overrides):
        return {
            "department": self.department.pk,
            "procedure": "CT head without contrast",
            "priority": OrderPriority.ROUTINE.value,
            "notes": "Rule out bleed.",
            **overrides,
        }

    def test_form_opens_for_an_assigned_patient(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["patient"], self.patient)

    def test_placing_an_order_records_the_doctor_and_patient(self):
        response = self.client.post(self.url, self.payload())
        order = ServiceOrder.objects.get()
        self.assertRedirects(
            response, reverse("orders:order_detail", args=[order.pk])
        )
        self.assertEqual(order.doctor, self.doctor)
        self.assertEqual(order.patient, self.patient)
        self.assertEqual(order.status, OrderStatus.ORDERED)

    def test_an_unassigned_patient_is_not_found(self):
        stranger = make_user("stranger", Role.PATIENT)
        url = reverse("orders:place_order", args=[stranger.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, self.payload()).status_code, 404)
        self.assertFalse(ServiceOrder.objects.exists())

    def test_a_submitted_patient_field_cannot_redirect_the_order(self):
        stranger = make_user("stranger", Role.PATIENT)
        self.client.post(self.url, self.payload(patient=stranger.pk))
        self.assertEqual(ServiceOrder.objects.get().patient, self.patient)

    def test_a_submitted_status_cannot_skip_the_queue(self):
        self.client.post(
            self.url, self.payload(status=OrderStatus.COMPLETED.value)
        )
        self.assertEqual(ServiceOrder.objects.get().status, OrderStatus.ORDERED)

    def test_an_urgent_order_keeps_its_priority(self):
        self.client.post(
            self.url, self.payload(priority=OrderPriority.URGENT.value)
        )
        self.assertEqual(
            ServiceOrder.objects.get().priority, OrderPriority.URGENT
        )

    def test_an_inactive_department_cannot_be_ordered_from(self):
        self.department.is_active = False
        self.department.save(update_fields=["is_active"])
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 200)
        self.assertIn("department", response.context["form"].errors)
        self.assertFalse(ServiceOrder.objects.exists())

    def test_a_missing_procedure_is_rejected(self):
        response = self.client.post(self.url, self.payload(procedure=""))
        self.assertEqual(response.status_code, 200)
        self.assertIn("procedure", response.context["form"].errors)
        self.assertFalse(ServiceOrder.objects.exists())

    def test_a_patient_cannot_place_orders(self):
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 403)

    def test_an_unapproved_doctor_is_sent_to_pending(self):
        self.client.force_login(make_user("newdoc", Role.DOCTOR, is_approved=False))
        self.assertRedirects(
            self.client.get(self.url), reverse("accounts:pending")
        )


class DoctorOrderListTests(OrderViewTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("orders:doctor_orders")

    def listed(self, **params):
        return list(self.client.get(self.url, params).context["orders"])

    def test_open_orders_are_shown_by_default(self):
        placed = self.order(procedure="Open one")
        done = self.order(procedure="Done one")
        done.complete()
        self.assertEqual(self.listed(), [placed])

    def test_closed_scope_shows_finished_and_cancelled_orders(self):
        self.order(procedure="Open one")
        done = self.order(procedure="Done one")
        done.complete()
        cancelled = self.order(procedure="Cancelled one")
        cancelled.cancel()
        self.assertEqual(set(self.listed(scope="closed")), {done, cancelled})

    def test_an_unknown_scope_falls_back_to_open(self):
        placed = self.order()
        self.assertEqual(self.listed(scope="everything"), [placed])

    def test_another_doctors_orders_are_not_listed(self):
        self.order(doctor=self.other_doctor)
        self.assertEqual(self.listed(), [])

    def test_a_patient_cannot_open_the_order_list(self):
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(self.url).status_code, 403)


class OrderDetailAndCancelTests(OrderViewTestCase):
    def setUp(self):
        super().setUp()
        self.order_obj = self.order()
        self.detail_url = reverse("orders:order_detail", args=[self.order_obj.pk])
        self.cancel_url = reverse("orders:cancel_order", args=[self.order_obj.pk])

    def test_own_order_opens(self):
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["order"], self.order_obj)

    def test_another_doctors_order_is_not_found(self):
        self.order_obj.doctor = self.other_doctor
        self.order_obj.save(update_fields=["doctor"])
        self.assertEqual(self.client.get(self.detail_url).status_code, 404)

    def test_cancelling_withdraws_an_unstarted_order(self):
        response = self.client.post(self.cancel_url)
        self.assertRedirects(response, self.detail_url)
        self.order_obj.refresh_from_db()
        self.assertEqual(self.order_obj.status, OrderStatus.CANCELLED)

    def test_a_started_order_cannot_be_cancelled(self):
        self.order_obj.start()
        self.assertEqual(self.client.post(self.cancel_url).status_code, 404)
        self.order_obj.refresh_from_db()
        self.assertEqual(self.order_obj.status, OrderStatus.IN_PROGRESS)

    def test_another_doctors_order_cannot_be_cancelled(self):
        self.order_obj.doctor = self.other_doctor
        self.order_obj.save(update_fields=["doctor"])
        self.assertEqual(self.client.post(self.cancel_url).status_code, 404)
        self.order_obj.refresh_from_db()
        self.assertEqual(self.order_obj.status, OrderStatus.ORDERED)

    def test_cancelling_requires_a_post(self):
        self.assertEqual(self.client.get(self.cancel_url).status_code, 405)


class PatientRecordOrdersTests(OrderViewTestCase):
    def test_orders_from_any_doctor_appear_on_the_record(self):
        mine = self.order(procedure="Mine")
        theirs = self.order(procedure="Theirs", doctor=self.other_doctor)
        response = self.client.get(
            reverse("records:patient_detail", args=[self.patient.pk])
        )
        self.assertEqual(set(response.context["orders"]), {mine, theirs})

    def test_another_patients_orders_stay_off_the_record(self):
        other_patient = make_user("pat2", Role.PATIENT)
        self.order(patient=other_patient, procedure="Elsewhere")
        response = self.client.get(
            reverse("records:patient_detail", args=[self.patient.pk])
        )
        self.assertEqual(list(response.context["orders"]), [])
