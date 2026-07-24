from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="accounts/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("register/done/", views.register_done, name="register_done"),
    path("pending/", views.pending, name="pending"),
    path("approvals/", views.PendingApprovalsView.as_view(), name="approvals"),
    path(
        "approvals/<int:pk>/approve/",
        views.ApproveUserView.as_view(),
        name="approve",
    ),
    path(
        "approvals/<int:pk>/reject/",
        views.RejectUserView.as_view(),
        name="reject",
    ),
]
