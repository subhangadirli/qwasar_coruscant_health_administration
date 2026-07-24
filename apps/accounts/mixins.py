from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


class ApprovedRequiredMixin(LoginRequiredMixin):
    """Require an authenticated user whose account an admin has approved.

    Unapproved users are sent to the pending-approval page instead of the
    protected view. Staff/superusers bypass the approval gate.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_approved or request.user.is_staff):
            return redirect("accounts:pending")
        return super().dispatch(request, *args, **kwargs)


class RoleRequiredMixin(ApprovedRequiredMixin):
    """Restrict a view to one or more roles (in addition to approval).

    Set ``allowed_roles`` to a tuple of Role values. Staff bypass the check.
    """

    allowed_roles = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_approved or request.user.is_staff):
            return redirect("accounts:pending")
        if (
            self.allowed_roles
            and not request.user.is_staff
            and request.user.role not in self.allowed_roles
        ):
            raise PermissionDenied
        return super(ApprovedRequiredMixin, self).dispatch(
            request, *args, **kwargs
        )
