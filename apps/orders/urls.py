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
]
