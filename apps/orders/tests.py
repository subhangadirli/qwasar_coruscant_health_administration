from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.test import TestCase

from apps.accounts.models import Role

from .models import (
    Department,
    DepartmentKind,
    OrderPriority,
    OrderStatus,
    ServiceOrder,
)

User = get_user_model()


def make_user(username, role):
    return User.objects.create_user(
        username=username, password="pw", role=role, is_approved=True
    )


class OrderTestCase(TestCase):
    def setUp(self):
        self.doctor = make_user("doc", Role.DOCTOR)
        self.patient = make_user("pat", Role.PATIENT)
        self.department = Department.objects.create(
            name="Imaging", kind=DepartmentKind.CT
        )

    def order(self, **overrides):
        fields = {
            "patient": self.patient,
            "doctor": self.doctor,
            "department": self.department,
            "procedure": "CT head without contrast",
            **overrides,
        }
        return ServiceOrder.objects.create(**fields)


class DepartmentTests(OrderTestCase):
    def test_str_names_the_service(self):
        self.assertEqual(str(self.department), "Imaging (CT scan)")

    def test_names_are_unique(self):
        from django.db.utils import IntegrityError

        with self.assertRaises(IntegrityError):
            Department.objects.create(name="Imaging", kind=DepartmentKind.MRI)

    def test_department_staff_can_be_attached(self):
        staffer = make_user("dept", Role.DEPARTMENT)
        self.department.staff.add(staffer)
        self.assertEqual(list(staffer.departments.all()), [self.department])


class ServiceOrderTests(OrderTestCase):
    def test_a_new_order_starts_as_ordered_and_routine(self):
        order = self.order()
        self.assertEqual(order.status, OrderStatus.ORDERED)
        self.assertEqual(order.priority, OrderPriority.ROUTINE)
        self.assertIsNone(order.completed_at)
        self.assertTrue(order.is_open)
        self.assertTrue(order.can_cancel)

    def test_str_reads_as_the_request(self):
        self.assertEqual(
            str(self.order()), "CT head without contrast for pat"
        )

    def test_starting_moves_it_to_in_progress(self):
        order = self.order()
        order.start()
        self.assertEqual(order.status, OrderStatus.IN_PROGRESS)
        self.assertTrue(order.is_open)
        self.assertFalse(order.can_cancel)

    def test_an_order_cannot_be_started_twice(self):
        order = self.order()
        order.start()
        with self.assertRaises(ValueError):
            order.start()

    def test_completing_stamps_the_time(self):
        order = self.order()
        order.start()
        order.complete()
        self.assertEqual(order.status, OrderStatus.COMPLETED)
        self.assertIsNotNone(order.completed_at)
        self.assertFalse(order.is_open)

    def test_an_unstarted_order_can_be_completed_directly(self):
        order = self.order()
        order.complete()
        self.assertEqual(order.status, OrderStatus.COMPLETED)

    def test_a_closed_order_cannot_be_completed_again(self):
        order = self.order()
        order.complete()
        with self.assertRaises(ValueError):
            order.complete()

    def test_cancelling_is_allowed_before_work_starts(self):
        order = self.order()
        order.cancel()
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertFalse(order.is_open)

    def test_a_started_order_cannot_be_cancelled(self):
        order = self.order()
        order.start()
        with self.assertRaises(ValueError):
            order.cancel()
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.IN_PROGRESS)

    def test_a_completed_order_cannot_be_cancelled(self):
        order = self.order()
        order.complete()
        with self.assertRaises(ValueError):
            order.cancel()

    def test_open_and_closed_split_the_queue(self):
        ordered = self.order(procedure="Ordered")
        started = self.order(procedure="Started")
        started.start()
        done = self.order(procedure="Done")
        done.complete()
        cancelled = self.order(procedure="Cancelled")
        cancelled.cancel()

        self.assertEqual(
            set(ServiceOrder.objects.open()), {ordered, started}
        )
        self.assertEqual(
            set(ServiceOrder.objects.closed()), {done, cancelled}
        )

    def test_newest_orders_come_first(self):
        first = self.order(procedure="First")
        second = self.order(procedure="Second")
        self.assertEqual(list(ServiceOrder.objects.all()), [second, first])

    def test_orders_are_reachable_from_the_patient_and_the_doctor(self):
        order = self.order()
        self.assertEqual(list(self.patient.service_orders.all()), [order])
        self.assertEqual(list(self.doctor.placed_orders.all()), [order])

    def test_deleting_the_patient_takes_their_orders(self):
        self.order()
        self.patient.delete()
        self.assertFalse(ServiceOrder.objects.exists())

    def test_the_ordering_doctor_cannot_be_deleted(self):
        self.order()
        with self.assertRaises(ProtectedError):
            self.doctor.delete()

    def test_a_department_with_orders_cannot_be_deleted(self):
        self.order()
        with self.assertRaises(ProtectedError):
            self.department.delete()
