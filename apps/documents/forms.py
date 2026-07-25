from django import forms

from .models import Document


class DocumentUploadForm(forms.ModelForm):
    """Upload a single file.

    ``owner``, ``patient`` and the derived metadata (name, type, size,
    checksum) are set from the request in the view, not the form, so they
    cannot be spoofed by the submitter.
    """

    class Meta:
        model = Document
        fields = ("file",)
        widgets = {
            "file": forms.ClearableFileInput(
                attrs={"class": "block w-full text-sm text-slate-600"}
            )
        }
