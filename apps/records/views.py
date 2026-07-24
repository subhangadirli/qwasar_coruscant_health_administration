from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, FormView, ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.accounts.models import Role

from .forms import HealthReadingForm, ReadingCSVUploadForm
from .models import MetricType, ReadingSource


class PatientReadingsView(RoleRequiredMixin, ListView):
    """A patient's own health readings, newest first, optionally filtered."""

    allowed_roles = (Role.PATIENT,)
    template_name = "records/reading_list.html"
    context_object_name = "readings"
    paginate_by = 25

    def get_selected_metric(self):
        metric = self.request.GET.get("metric")
        return metric if metric in MetricType.values else None

    def get_queryset(self):
        # Scoped to the requesting user, so one patient can never read
        # another's readings by guessing a query parameter.
        queryset = self.request.user.health_readings.all()
        metric = self.get_selected_metric()
        if metric:
            queryset = queryset.filter(metric=metric)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["metric_choices"] = MetricType.choices
        context["selected_metric"] = self.get_selected_metric()
        return context


class AddReadingView(RoleRequiredMixin, CreateView):
    """Manual entry of a single reading by the patient."""

    allowed_roles = (Role.PATIENT,)
    form_class = HealthReadingForm
    template_name = "records/reading_form.html"
    success_url = reverse_lazy("records:readings")

    def form_valid(self, form):
        form.instance.patient = self.request.user
        form.instance.source = ReadingSource.MANUAL
        messages.success(self.request, "Reading saved.")
        return super().form_valid(form)


class UploadReadingsCSVView(RoleRequiredMixin, FormView):
    """Bulk import of a device CSV export for the logged-in patient."""

    allowed_roles = (Role.PATIENT,)
    form_class = ReadingCSVUploadForm
    template_name = "records/reading_upload.html"
    success_url = reverse_lazy("records:readings")

    def form_valid(self, form):
        created = form.save(self.request.user)
        messages.success(self.request, f"Imported {len(created)} reading(s).")
        return super().form_valid(form)
