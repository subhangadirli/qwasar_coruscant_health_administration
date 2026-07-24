from django.urls import path

from . import views

app_name = "records"

urlpatterns = [
    path("readings/", views.PatientReadingsView.as_view(), name="readings"),
    path("readings/add/", views.AddReadingView.as_view(), name="add_reading"),
    path(
        "readings/upload/",
        views.UploadReadingsCSVView.as_view(),
        name="upload_readings",
    ),
    path("device-token/", views.DeviceTokenView.as_view(), name="device_token"),
    path("api/readings/", views.device_readings_ingest, name="api_readings"),
    path("patients/", views.DoctorPatientsView.as_view(), name="patients"),
    path(
        "patients/<int:pk>/",
        views.DoctorPatientDetailView.as_view(),
        name="patient_detail",
    ),
    path("reports/", views.PatientReportsView.as_view(), name="reports"),
    path(
        "reports/<int:pk>/",
        views.PatientReportDetailView.as_view(),
        name="report_detail",
    ),
]
