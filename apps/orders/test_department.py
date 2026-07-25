import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role

from .models import (
    Department,
    DepartmentKind,
    OrderResult,
    OrderStatus,
    ServiceOrder,
)

User = get_user_model()

# Route result-file uploads to a throwaway directory so tests never leave
# artefacts in the project's media/ folder.
_TEST_MEDIA = tempfile.mkdtemp(prefix="cha-orders-test-")


def tearDownModule():
    shutil.rmtree(_TEST_MEDIA, ignore_errors=True)


def make_user(username, role, **extra):
    return User.objects.create_user(
        username=username,
        password="pw",
        role=role,
        is_approved=extra.pop("is_approved", True),
        **extra,
    )


@override_settings(MEDIA_ROOT=_TEST_MEDIA)
class DepartmentTestCase(TestCase):
    def setUp(self):
        self.doctor = make_user("doc", Role.DOCTOR)
        self.patient = make_user("pat", Role.PATIENT)
        self.dept_user = make_user("radiology", Role.DEPARTMENT)
        self.department = Department.objects.create(
            name="Imaging", kind=DepartmentKind.CT
        )
        self.department.staff.add(self.dept_user)

    def order(self, **overrides):
        fields = {
            "patient": self.patient,
            "doctor": self.doctor,
            "department": self.department,
            "procedure": "CT head without contrast",
            **overrides,
        }
        return ServiceOrder.objects.create(**fields)


class DepartmentQueueTests(DepartmentTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("orders:department_queue")
        self.client.force_login(self.dept_user)

    def listed(self, **params):
        return list(self.client.get(self.url, params).context["orders"])

    def test_open_orders_for_the_department_are_shown_by_default(self):
        placed = self.order()
        done = self.order(procedure="Done one")
        done.complete()
        self.assertEqual(self.listed(), [placed])

    def test_closed_scope_shows_finished_and_cancelled(self):
        done = self.order(procedure="Done one")
        done.complete()
        cancelled = self.order(procedure="Cancelled one")
        cancelled.cancel()
        self.assertEqual(set(self.listed(scope="closed")), {done, cancelled})

    def test_another_departments_orders_are_not_shown(self):
        other_dept = Department.objects.create(
            name="Lab", kind=DepartmentKind.LAB
        )
        self.order(department=other_dept)
        self.assertEqual(self.listed(), [])

    def test_a_department_only_sees_queues_it_staffs(self):
        stranger = make_user("labtech", Role.DEPARTMENT)
        self.client.force_login(stranger)
        self.order()
        self.assertEqual(self.listed(), [])

    def test_a_doctor_cannot_open_the_queue(self):
        self.client.force_login(self.doctor)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_an_unapproved_department_is_sent_to_pending(self):
        self.client.force_login(
            make_user("newdept", Role.DEPARTMENT, is_approved=False)
        )
        self.assertRedirects(
            self.client.get(self.url), reverse("accounts:pending")
        )


class DepartmentDetailAndStartTests(DepartmentTestCase):
    def setUp(self):
        super().setUp()
        self.order_obj = self.order()
        self.detail_url = reverse(
            "orders:department_order", args=[self.order_obj.pk]
        )
        self.start_url = reverse("orders:start_order", args=[self.order_obj.pk])
        self.client.force_login(self.dept_user)

    def test_own_departments_order_opens(self):
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["order"], self.order_obj)

    def test_another_departments_order_is_not_found(self):
        other_dept = Department.objects.create(
            name="Lab", kind=DepartmentKind.LAB
        )
        self.order_obj.department = other_dept
        self.order_obj.save(update_fields=["department"])
        self.assertEqual(self.client.get(self.detail_url).status_code, 404)

    def test_starting_moves_the_order_into_progress(self):
        response = self.client.post(self.start_url)
        self.assertRedirects(response, self.detail_url)
        self.order_obj.refresh_from_db()
        self.assertEqual(self.order_obj.status, OrderStatus.IN_PROGRESS)

    def test_starting_requires_a_post(self):
        self.assertEqual(self.client.get(self.start_url).status_code, 405)

    def test_a_started_order_can_no_longer_be_cancelled_by_the_doctor(self):
        self.client.post(self.start_url)
        self.client.force_login(self.doctor)
        cancel_url = reverse("orders:cancel_order", args=[self.order_obj.pk])
        self.assertEqual(self.client.post(cancel_url).status_code, 404)


class CompleteOrderTests(DepartmentTestCase):
    def setUp(self):
        super().setUp()
        self.order_obj = self.order()
        self.order_obj.start()
        self.url = reverse("orders:complete_order", args=[self.order_obj.pk])
        self.detail_url = reverse(
            "orders:department_order", args=[self.order_obj.pk]
        )
        self.client.force_login(self.dept_user)

    def test_completing_records_a_result_and_closes_the_order(self):
        response = self.client.post(self.url, {"summary": "No acute finding."})
        self.assertRedirects(response, self.detail_url)
        self.order_obj.refresh_from_db()
        self.assertEqual(self.order_obj.status, OrderStatus.COMPLETED)
        self.assertIsNotNone(self.order_obj.completed_at)
        result = self.order_obj.result
        self.assertEqual(result.summary, "No acute finding.")
        self.assertEqual(result.uploaded_by, self.dept_user)

    def test_a_result_attachment_is_stored(self):
        upload = SimpleUploadedFile(
            "scan.txt", b"pixels", content_type="text/plain"
        )
        self.client.post(
            self.url, {"summary": "See attached.", "attachment": upload}
        )
        self.assertTrue(self.order_obj.result.attachment)

    def test_a_missing_summary_is_rejected(self):
        response = self.client.post(self.url, {"summary": ""})
        self.assertEqual(response.status_code, 200)
        self.assertIn("summary", response.context["form"].errors)
        self.assertFalse(OrderResult.objects.exists())
        self.order_obj.refresh_from_db()
        self.assertEqual(self.order_obj.status, OrderStatus.IN_PROGRESS)

    def test_an_unstarted_order_cannot_be_completed(self):
        fresh = self.order()
        url = reverse("orders:complete_order", args=[fresh.pk])
        response = self.client.post(url, {"summary": "Too soon."})
        self.assertRedirects(
            response, reverse("orders:department_order", args=[fresh.pk])
        )
        fresh.refresh_from_db()
        self.assertEqual(fresh.status, OrderStatus.ORDERED)
        self.assertFalse(OrderResult.objects.exists())

    def test_another_departments_order_cannot_be_completed(self):
        stranger = make_user("labtech", Role.DEPARTMENT)
        self.client.force_login(stranger)
        self.assertEqual(
            self.client.post(self.url, {"summary": "Nope."}).status_code, 404
        )


class ResultDownloadTests(DepartmentTestCase):
    def setUp(self):
        super().setUp()
        self.order_obj = self.order(status=OrderStatus.COMPLETED)
        self.result = OrderResult.objects.create(
            order=self.order_obj,
            summary="See attached.",
            uploaded_by=self.dept_user,
            attachment=SimpleUploadedFile(
                "scan.txt", b"pixels", content_type="text/plain"
            ),
        )
        self.url = reverse("orders:download_result", args=[self.result.pk])

    def test_the_ordering_doctor_can_download(self):
        self.client.force_login(self.doctor)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_the_patient_can_download(self):
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_the_department_staff_can_download(self):
        self.client.force_login(self.dept_user)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_an_unrelated_user_gets_a_404(self):
        stranger = make_user("stranger", Role.PATIENT)
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_anonymous_users_are_sent_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)


class PatientOrderVisibilityTests(DepartmentTestCase):
    def setUp(self):
        super().setUp()
        self.list_url = reverse("orders:patient_orders")
        self.client.force_login(self.patient)

    def test_a_patient_sees_their_own_orders(self):
        mine = self.order()
        response = self.client.get(self.list_url)
        self.assertEqual(list(response.context["orders"]), [mine])

    def test_another_patients_orders_are_hidden(self):
        other = make_user("pat2", Role.PATIENT)
        self.order(patient=other)
        response = self.client.get(self.list_url)
        self.assertEqual(list(response.context["orders"]), [])

    def test_another_patients_order_detail_is_not_found(self):
        other = make_user("pat2", Role.PATIENT)
        theirs = self.order(patient=other)
        url = reverse("orders:patient_order", args=[theirs.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_a_completed_order_shows_its_result_to_the_patient(self):
        order = self.order(status=OrderStatus.COMPLETED)
        OrderResult.objects.create(
            order=order, summary="All clear.", uploaded_by=self.dept_user
        )
        url = reverse("orders:patient_order", args=[order.pk])
        response = self.client.get(url)
        self.assertContains(response, "All clear.")

    def test_a_doctor_cannot_open_the_patient_order_list(self):
        self.client.force_login(self.doctor)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
