from django.http import JsonResponse
from django.shortcuts import redirect, render

from apps.accounts.models import Role

# Which template each role lands on after login.
ROLE_DASHBOARDS = {
    Role.PATIENT: "dashboard/patient.html",
    Role.DOCTOR: "dashboard/doctor.html",
    Role.DEPARTMENT: "dashboard/department.html",
    Role.ADMIN: "dashboard/admin.html",
    Role.EMERGENCY: "dashboard/emergency.html",
}


def health_check(request):
    """Lightweight liveness endpoint for the platform's health probe."""
    return JsonResponse({"status": "ok"})


def home(request):
    """Landing page; routes authenticated users to their role dashboard."""
    if not request.user.is_authenticated:
        return render(request, "dashboard/home.html")

    if not (request.user.is_approved or request.user.is_staff):
        return redirect("accounts:pending")

    template = ROLE_DASHBOARDS.get(request.user.role, "dashboard/home.html")
    return render(request, template)
