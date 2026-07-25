from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, FormView, ListView, View

from .forms import EmergencyIntakeForm, RegistrationForm
from .intake import admit_emergency_patient
from .mixins import EmergencyRequiredMixin, RoleRequiredMixin
from .models import Role, User


class RegisterView(CreateView):
    """Public sign-up for patients and doctors (created unapproved)."""

    form_class = RegistrationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("accounts:register_done")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard:home")
        return super().dispatch(request, *args, **kwargs)


def register_done(request):
    return render(request, "accounts/register_done.html")


def pending(request):
    """Shown to logged-in users still awaiting admin approval."""
    return render(request, "accounts/pending.html")


class EmergencyIntakeView(EmergencyRequiredMixin, FormView):
    """Fast intake screen for the emergency desk.

    A successful submission provisions an approved patient and re-renders the
    screen with a confirmation and a blank form, since a desk admits patients
    one after another.
    """

    template_name = "accounts/emergency_intake.html"
    form_class = EmergencyIntakeForm

    def form_valid(self, form):
        intake = admit_emergency_patient(
            full_name=form.cleaned_data["full_name"],
            admitted_by=self.request.user,
            presenting_complaint=form.cleaned_data["presenting_complaint"],
        )
        context = self.get_context_data(form=self.form_class(), admitted=intake)
        return self.render_to_response(context)


class AdminRequiredMixin(RoleRequiredMixin):
    """Only administrators (role=admin) or Django staff may manage approvals."""

    allowed_roles = (Role.ADMIN,)


class PendingApprovalsView(AdminRequiredMixin, ListView):
    """In-app queue of accounts awaiting acknowledgment."""

    template_name = "accounts/approvals.html"
    context_object_name = "pending_users"

    def get_queryset(self):
        return User.objects.filter(
            is_approved=False, is_rejected=False, is_staff=False
        ).order_by("date_joined")


class ApproveUserView(AdminRequiredMixin, View):
    def post(self, request, pk):
        user = get_object_or_404(
            User, pk=pk, is_approved=False, is_rejected=False, is_staff=False
        )
        user.is_approved = True
        user.save(update_fields=["is_approved"])
        messages.success(request, f"Approved {user.username}.")
        return redirect("accounts:approvals")


class RejectUserView(AdminRequiredMixin, View):
    def post(self, request, pk):
        user = get_object_or_404(
            User, pk=pk, is_approved=False, is_rejected=False, is_staff=False
        )
        user.is_rejected = True
        user.is_active = False
        user.save(update_fields=["is_rejected", "is_active"])
        messages.info(request, f"Rejected {user.username}.")
        return redirect("accounts:approvals")
