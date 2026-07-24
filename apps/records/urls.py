from django.urls import path

from . import views

app_name = "records"

urlpatterns = [
    path("readings/", views.PatientReadingsView.as_view(), name="readings"),
]
