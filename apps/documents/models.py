import hashlib

from django.conf import settings
from django.db import models

from apps.accounts.models import Role


def sha256_of(upload):
    """Hex SHA-256 of an uploaded file, read in chunks and rewound after.

    Computed over the plaintext at upload time so a later download can prove
    the bytes came back exactly as they went in, independent of the storage
    layer underneath.
    """
    hasher = hashlib.sha256()
    for chunk in upload.chunks():
        hasher.update(chunk)
    upload.seek(0)
    return hasher.hexdigest()


class Document(models.Model):
    """A file uploaded to a patient's record.

    ``owner`` is who uploaded it — a patient adding to their own record, or a
    doctor adding to an assigned patient's. ``patient`` is whose record it
    belongs to and drives who may read it. Files are stored privately and
    served only through an access-checked download view, never a public URL.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        # A document is part of the patient's record, so it outlives the
        # uploader's account.
        on_delete=models.PROTECT,
        related_name="uploaded_documents",
    )
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
        limit_choices_to={"role": Role.PATIENT},
    )
    file = models.FileField(upload_to="documents/")
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    checksum = models.CharField(
        max_length=64,
        help_text="SHA-256 of the file's plaintext, for integrity checks.",
    )
    size = models.PositiveIntegerField(
        default=0, help_text="Plaintext size in bytes."
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-uploaded_at",)
        indexes = [models.Index(fields=["patient", "-uploaded_at"])]

    def __str__(self):
        return self.original_name
