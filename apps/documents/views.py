from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView

from apps.accounts.mixins import AssignedPatientMixin, RoleRequiredMixin
from apps.accounts.models import PatientDoctorAssignment, Role

from .forms import DocumentUploadForm
from .models import Document, sha256_of


class DocumentUploadMixin:
    """Shared upload plumbing: derive the file metadata from the upload.

    Subclasses set ``owner`` and ``patient`` on the instance in their own
    ``form_valid`` before calling ``super()``.
    """

    form_class = DocumentUploadForm

    def stamp_upload(self, form):
        upload = form.cleaned_data["file"]
        form.instance.original_name = upload.name
        form.instance.content_type = getattr(upload, "content_type", "") or ""
        form.instance.size = upload.size
        form.instance.checksum = sha256_of(upload)


class PatientDocumentsView(RoleRequiredMixin, DocumentUploadMixin, CreateView):
    """A patient's own documents, with an upload form."""

    allowed_roles = (Role.PATIENT,)
    template_name = "documents/patient_documents.html"

    def form_valid(self, form):
        form.instance.owner = self.request.user
        form.instance.patient = self.request.user
        self.stamp_upload(form)
        messages.success(self.request, "Document uploaded.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("documents:patient_documents")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["documents"] = self.request.user.documents.select_related("owner")
        return context


class DoctorPatientDocumentsView(
    AssignedPatientMixin, DocumentUploadMixin, CreateView
):
    """Documents on an assigned patient's record, with an upload form."""

    template_name = "documents/doctor_patient_documents.html"

    def form_valid(self, form):
        form.instance.owner = self.request.user
        form.instance.patient = self.get_patient()
        self.stamp_upload(form)
        messages.success(self.request, "Document uploaded.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            "documents:doctor_patient_documents", args=[self.get_patient().pk]
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        patient = self.get_patient()
        context["patient"] = patient
        context["documents"] = patient.documents.select_related("owner")
        return context


class DocumentDownloadView(LoginRequiredMixin, View):
    """Stream a document to anyone entitled to the patient's record.

    Serving through a permission-checked view rather than a public media URL
    is what keeps documents private.
    """

    def get(self, request, pk):
        document = get_object_or_404(
            Document.objects.select_related("patient", "owner"), pk=pk
        )
        if not self._may_access(request.user, document):
            raise Http404("No such document.")
        return FileResponse(
            document.file.open("rb"),
            as_attachment=True,
            filename=document.original_name,
        )

    @staticmethod
    def _may_access(user, document):
        if user == document.patient or user == document.owner:
            return True
        return user.is_doctor and PatientDoctorAssignment.is_assigned(
            user, document.patient
        )
