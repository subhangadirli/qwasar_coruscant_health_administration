from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, FormView, ListView

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
    # Enough history to show a trend without shipping a huge payload.
    chart_point_limit = 100

    def get_selected_metric(self):
        metric = self.request.GET.get("metric")
        return metric if metric in MetricType.values else None

    def get_chart_metric(self):
        """Metric to plot: the filtered one, else the most recently recorded.

        A chart mixing metrics would put incompatible units on one axis, so
        the trend is always for a single metric.
        """
        selected = self.get_selected_metric()
        if selected:
            return selected
        latest = self.request.user.health_readings.first()
        return latest.metric if latest else None

    def get_chart_data(self):
        metric = self.get_chart_metric()
        if not metric:
            return None

        readings = list(
            self.request.user.health_readings.filter(metric=metric).order_by(
                "-recorded_at"
            )[: self.chart_point_limit]
        )
        if not readings:
            return None
        readings.reverse()  # a trend line reads oldest to newest

        return {
            "metric": metric,
            "label": MetricType(metric).label,
            "unit": readings[0].unit,
            "labels": [r.recorded_at.isoformat() for r in readings],
            "values": [float(r.value) for r in readings],
        }

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
        context["chart_data"] = self.get_chart_data()
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


class PatientReportsMixin(RoleRequiredMixin):
    """Restrict reports to the ones published for the logged-in patient.

    Scoping the queryset rather than checking after lookup means an
    unpublished report, or another patient's, is simply a 404.
    """

    allowed_roles = (Role.PATIENT,)

    def get_queryset(self):
        return self.request.user.reports.published().select_related("doctor")


class PatientReportsView(PatientReportsMixin, ListView):
    template_name = "records/report_list.html"
    context_object_name = "reports"
    paginate_by = 20


class PatientReportDetailView(PatientReportsMixin, DetailView):
    template_name = "records/report_detail.html"
    context_object_name = "report"
