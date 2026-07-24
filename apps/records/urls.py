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
    path("reports/", views.PatientReportsView.as_view(), name="reports"),
    path(
        "reports/<int:pk>/",
        views.PatientReportDetailView.as_view(),
        name="report_detail",
    ),
]
