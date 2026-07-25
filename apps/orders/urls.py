from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("", views.DoctorOrdersView.as_view(), name="doctor_orders"),
    path(
        "patients/<int:pk>/new/",
        views.PlaceOrderView.as_view(),
        name="place_order",
    ),
    path("<int:pk>/", views.OrderDetailView.as_view(), name="order_detail"),
    path(
        "<int:pk>/cancel/", views.CancelOrderView.as_view(), name="cancel_order"
    ),
    path("queue/", views.DepartmentQueueView.as_view(), name="department_queue"),
    path(
        "queue/<int:pk>/",
        views.DepartmentOrderDetailView.as_view(),
        name="department_order",
    ),
    path(
        "queue/<int:pk>/start/",
        views.StartOrderView.as_view(),
        name="start_order",
    ),
    path(
        "queue/<int:pk>/complete/",
        views.CompleteOrderView.as_view(),
        name="complete_order",
    ),
    path(
        "results/<int:pk>/download/",
        views.OrderResultDownloadView.as_view(),
        name="download_result",
    ),
    path("my/", views.PatientOrdersView.as_view(), name="patient_orders"),
    path(
        "my/<int:pk>/",
        views.PatientOrderDetailView.as_view(),
        name="patient_order",
    ),
]
