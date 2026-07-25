"""Encryption-at-rest for uploaded documents.

Files are Fernet-encrypted before they touch disk and decrypted only in
memory when re-opened, so a leaked ``MEDIA_ROOT`` yields ciphertext rather
than patient records. Nothing here is served from a public URL — downloads go
through an access-checked view. Moving to a KMS-backed or S3 store later means
replacing this class, not the models or views that use it.
"""

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, SuspiciousOperation
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage


class EncryptedFileSystemStorage(FileSystemStorage):
    """A private filesystem store that encrypts file contents at rest."""

    def _fernet(self):
        # Read the key lazily, per operation, so override_settings in tests and
        # a rotated key in prod both take effect without reinstantiating fields.
        key = getattr(settings, "DOCUMENT_ENCRYPTION_KEY", None)
        if not key:
            raise ImproperlyConfigured(
                "DOCUMENT_ENCRYPTION_KEY must be set to store documents."
            )
        return Fernet(key.encode() if isinstance(key, str) else key)

    def _save(self, name, content):
        token = self._fernet().encrypt(content.read())
        return super()._save(name, ContentFile(token))

    def _open(self, name, mode="rb"):
        with super()._open(name, "rb") as handle:
            token = handle.read()
        try:
            plaintext = self._fernet().decrypt(token)
        except InvalidToken as exc:
            # A bad key or tampered ciphertext must never surface as content.
            raise SuspiciousOperation(
                "Stored document could not be decrypted."
            ) from exc
        return ContentFile(plaintext)


def encrypted_storage():
    """Callable storage for the ``file`` field.

    Passed as a callable so migrations reference it by import path and the key
    is only ever consulted at read/write time, not at model-load time.
    """
    return EncryptedFileSystemStorage()
