from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.PatientDocumentsView.as_view(), name="patient_documents"),
    path(
        "patients/<int:pk>/",
        views.DoctorPatientDocumentsView.as_view(),
        name="doctor_patient_documents",
    ),
    path(
        "<int:pk>/download/",
        views.DocumentDownloadView.as_view(),
        name="download_document",
    ),
]
