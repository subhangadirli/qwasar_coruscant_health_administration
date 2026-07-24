from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect

from .models import PatientDoctorAssignment, Role


class ApprovedRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Require an authenticated user whose account an admin has approved.

    Unapproved users are sent to the pending-approval page instead of the
    protected view. Staff/superusers bypass the approval gate.
    """

    def test_func(self):
        return self.request.user.is_approved or self.request.user.is_staff

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        return redirect("accounts:pending")


class RoleRequiredMixin(ApprovedRequiredMixin):
    """Restrict a view to one or more roles (in addition to approval).

    Set ``allowed_roles`` to a tuple of Role values. Staff bypass the check.
    """

    allowed_roles = ()

    def test_func(self):
        return super().test_func() and self._role_allowed()

    def _role_allowed(self):
        user = self.request.user
        return (
            not self.allowed_roles
            or user.is_staff
            or user.role in self.allowed_roles
        )

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        if not super().test_func():
            return redirect("accounts:pending")
        raise PermissionDenied


class DoctorRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.DOCTOR,)


class AssignedPatientMixin(DoctorRequiredMixin):
    """Resolve a patient only through this doctor's active assignments.

    Because the lookup is scoped rather than checked afterwards, a doctor
    who guesses the id of a patient they are not treating gets a 404 and
    learns nothing about whether that patient exists.
    """

    patient_url_kwarg = "pk"

    def get_patient(self):
        if not hasattr(self, "_patient"):
            self._patient = get_object_or_404(
                PatientDoctorAssignment.patients_of(self.request.user),
                pk=self.kwargs[self.patient_url_kwarg],
            )
        return self._patient
