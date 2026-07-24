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
    path(
        "patients/<int:pk>/reports/new/",
        views.WriteReportView.as_view(),
        name="write_report",
    ),
    path(
        "authored-reports/",
        views.DoctorReportsView.as_view(),
        name="doctor_reports",
    ),
    path(
        "authored-reports/<int:pk>/",
        views.DoctorReportDetailView.as_view(),
        name="doctor_report_detail",
    ),
    path(
        "authored-reports/<int:pk>/edit/",
        views.EditReportView.as_view(),
        name="edit_report",
    ),
    path(
        "authored-reports/<int:pk>/publish/",
        views.PublishReportView.as_view(),
        name="publish_report",
    ),
    path("reports/", views.PatientReportsView.as_view(), name="reports"),
    path(
        "reports/<int:pk>/",
        views.PatientReportDetailView.as_view(),
        name="report_detail",
    ),
]
