from django.http import JsonResponse
from django.shortcuts import render


def health_check(request):
    """Lightweight liveness endpoint for the platform's health probe."""
    return JsonResponse({"status": "ok"})


def home(request):
    """Landing page. Later this redirects to a role-specific dashboard."""
    return render(request, "dashboard/home.html")
