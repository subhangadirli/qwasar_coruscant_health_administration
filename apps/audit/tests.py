"""Tests for the audit trail and the sensitive-action hooks that write to it."""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction, AuditLog
from apps.audit.services import record


class RecordServiceTests(TestCase):
    def test_record_writes_a_row(self):
        actor = User.objects.create_user("desk", password="pw", role=Role.ADMIN)
        entry = record(AuditAction.USER_APPROVED, actor=actor, target="alice", detail="x")
        self.assertEqual(entry.actor, actor)
        self.assertEqual(entry.action, AuditAction.USER_APPROVED)
        self.assertEqual(entry.target, "alice")

    def test_record_tolerates_no_actor(self):
        entry = record(AuditAction.LOGIN, actor=None, target="system")
        self.assertIsNone(entry.actor)

    def test_long_fields_are_truncated(self):
        entry = record(AuditAction.LOGIN, target="x" * 500, detail="y" * 500)
        self.assertEqual(len(entry.target), 255)
        self.assertEqual(len(entry.detail), 255)


class LoginSignalTests(TestCase):
    def test_successful_login_is_logged(self):
        User.objects.create_user("bob", password="secret-pass-123", role=Role.PATIENT,
                                 is_approved=True)
        self.client.post(reverse("accounts:login"),
                         {"username": "bob", "password": "secret-pass-123"})
        entry = AuditLog.objects.get(action=AuditAction.LOGIN)
        self.assertEqual(entry.actor.username, "bob")
        self.assertEqual(entry.target, "bob")

    def test_failed_login_is_not_logged(self):
        User.objects.create_user("bob", password="secret-pass-123", role=Role.PATIENT,
                                 is_approved=True)
        self.client.post(reverse("accounts:login"),
                         {"username": "bob", "password": "wrong"})
        self.assertFalse(AuditLog.objects.filter(action=AuditAction.LOGIN).exists())


class ApprovalAuditTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", password="pw", role=Role.ADMIN,
                                               is_staff=True, is_approved=True)
        self.pending = User.objects.create_user("newdoc", password="pw", role=Role.DOCTOR)
        self.client.force_login(self.admin)

    def test_approve_is_logged(self):
        self.client.post(reverse("accounts:approve", args=[self.pending.pk]))
        entry = AuditLog.objects.get(action=AuditAction.USER_APPROVED)
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.target, "newdoc")

    def test_reject_is_logged(self):
        self.client.post(reverse("accounts:reject", args=[self.pending.pk]))
        entry = AuditLog.objects.get(action=AuditAction.USER_REJECTED)
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.target, "newdoc")
