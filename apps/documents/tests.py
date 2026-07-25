import hashlib
import shutil
import tempfile

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import PatientDoctorAssignment, Role
from apps.audit.models import AuditAction, AuditLog

from .models import Document

User = get_user_model()

# An isolated media root and a throwaway key, so tests neither touch the
# project's media/ nor depend on the deployment's encryption key.
_TEST_MEDIA = tempfile.mkdtemp(prefix="cha-documents-test-")
_TEST_KEY = Fernet.generate_key().decode()


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


@override_settings(MEDIA_ROOT=_TEST_MEDIA, DOCUMENT_ENCRYPTION_KEY=_TEST_KEY)
class DocumentTestCase(TestCase):
    def setUp(self):
        self.patient = make_user("pat", Role.PATIENT)
        self.doctor = make_user("doc", Role.DOCTOR)

    def upload(self, content=b"top secret vitals", name="vitals.txt"):
        return SimpleUploadedFile(name, content, content_type="text/plain")


class PatientUploadTests(DocumentTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("documents:patient_documents")
        self.client.force_login(self.patient)

    def test_a_patient_uploads_to_their_own_record(self):
        response = self.client.post(self.url, {"file": self.upload()})
        self.assertRedirects(response, self.url)
        document = Document.objects.get()
        self.assertEqual(document.owner, self.patient)
        self.assertEqual(document.patient, self.patient)
        self.assertEqual(document.original_name, "vitals.txt")
        self.assertEqual(document.size, len(b"top secret vitals"))

    def test_the_list_shows_only_the_patients_own_documents(self):
        Document.objects.create(
            owner=self.patient,
            patient=self.patient,
            file=ContentFile(b"mine", name="mine.txt"),
            original_name="mine.txt",
            checksum="x",
        )
        other = make_user("pat2", Role.PATIENT)
        Document.objects.create(
            owner=other,
            patient=other,
            file=ContentFile(b"theirs", name="theirs.txt"),
            original_name="theirs.txt",
            checksum="y",
        )
        response = self.client.get(self.url)
        names = [d.original_name for d in response.context["documents"]]
        self.assertEqual(names, ["mine.txt"])

    def test_a_doctor_cannot_open_the_patient_documents_page(self):
        self.client.force_login(self.doctor)
        self.assertEqual(self.client.get(self.url).status_code, 403)


class DoctorUploadTests(DocumentTestCase):
    def setUp(self):
        super().setUp()
        PatientDoctorAssignment.objects.create(
            patient=self.patient, doctor=self.doctor
        )
        self.url = reverse(
            "documents:doctor_patient_documents", args=[self.patient.pk]
        )
        self.client.force_login(self.doctor)

    def test_a_doctor_uploads_to_an_assigned_patients_record(self):
        response = self.client.post(self.url, {"file": self.upload()})
        self.assertRedirects(response, self.url)
        document = Document.objects.get()
        self.assertEqual(document.owner, self.doctor)
        self.assertEqual(document.patient, self.patient)

    def test_a_doctor_cannot_reach_an_unassigned_patients_documents(self):
        stranger = make_user("pat2", Role.PATIENT)
        url = reverse(
            "documents:doctor_patient_documents", args=[stranger.pk]
        )
        self.assertEqual(self.client.get(url).status_code, 404)


class EncryptionTests(DocumentTestCase):
    def test_the_file_is_ciphertext_on_disk_but_reads_back_as_plaintext(self):
        secret = b"top secret vitals"
        self.client.force_login(self.patient)
        self.client.post(
            reverse("documents:patient_documents"), {"file": self.upload(secret)}
        )
        document = Document.objects.get()

        with open(document.file.path, "rb") as handle:
            on_disk = handle.read()
        self.assertNotIn(secret, on_disk)
        self.assertTrue(on_disk.startswith(b"gAAAA"))  # Fernet token prefix

        self.assertEqual(document.file.open("rb").read(), secret)


class DownloadAccessTests(DocumentTestCase):
    def setUp(self):
        super().setUp()
        self.document = Document.objects.create(
            owner=self.patient,
            patient=self.patient,
            file=ContentFile(b"top secret vitals", name="vitals.txt"),
            original_name="vitals.txt",
            checksum=hashlib.sha256(b"top secret vitals").hexdigest(),
        )
        self.url = reverse(
            "documents:download_document", args=[self.document.pk]
        )

    def test_the_patient_can_download_their_own_document(self):
        self.client.force_login(self.patient)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"top secret vitals")

    def test_an_assigned_doctor_can_download(self):
        PatientDoctorAssignment.objects.create(
            patient=self.patient, doctor=self.doctor
        )
        self.client.force_login(self.doctor)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_an_unassigned_doctor_gets_a_404(self):
        self.client.force_login(self.doctor)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_another_patient_gets_a_404(self):
        self.client.force_login(make_user("pat2", Role.PATIENT))
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_anonymous_users_are_sent_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_a_tampered_file_fails_its_integrity_check(self):
        # Replace the stored ciphertext in place with a validly-encrypted but
        # different payload: it decrypts cleanly, yet its hash no longer
        # matches the recorded checksum, so the download must refuse it.
        token = Fernet(_TEST_KEY.encode()).encrypt(b"tampered contents")
        with open(self.document.file.path, "wb") as handle:
            handle.write(token)
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(self.url).status_code, 400)

    def test_a_successful_download_is_audited(self):
        self.client.force_login(self.patient)
        self.client.get(self.url)
        entry = AuditLog.objects.get(action=AuditAction.DOCUMENT_DOWNLOADED)
        self.assertEqual(entry.actor, self.patient)
        self.assertEqual(entry.target, "vitals.txt")

    def test_a_denied_download_is_not_audited(self):
        self.client.force_login(make_user("pat3", Role.PATIENT))
        self.client.get(self.url)
        self.assertFalse(
            AuditLog.objects.filter(action=AuditAction.DOCUMENT_DOWNLOADED).exists()
        )
