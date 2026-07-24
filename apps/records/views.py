import json

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView

from apps.accounts.mixins import RoleRequiredMixin
from apps.accounts.models import Role

from .forms import HealthReadingForm, ReadingCSVUploadForm
from .ingest import parse_reading_row
from .models import DeviceToken, HealthReading, MetricType, ReadingSource

# Bounds one device request; matches the spirit of the CSV row cap.
MAX_API_READINGS = 500


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


class DeviceTokenView(RoleRequiredMixin, TemplateView):
    """Issue and replace the bearer token a patient's device posts with."""

    allowed_roles = (Role.PATIENT,)
    template_name = "records/device_token.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["token"] = DeviceToken.objects.filter(
            patient=self.request.user
        ).first()
        return context

    def post(self, request, *args, **kwargs):
        _, raw_key = DeviceToken.issue(request.user)
        messages.success(
            request,
            "New device token issued. Copy it now; it cannot be shown again.",
        )
        # Rendered once and never stored in the session, so it cannot leak
        # through a later request.
        context = self.get_context_data(**kwargs)
        context["raw_key"] = raw_key
        return self.render_to_response(context)


def _bearer_token(request):
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return value.strip()


def _api_error(message, status, **extra):
    return JsonResponse({"error": message, **extra}, status=status)


@csrf_exempt
@require_POST
def device_readings_ingest(request):
    """Accept a batch of readings from an authenticated patient device.

    CSRF exemption is safe here because authentication is a bearer token,
    not the session cookie: a cross-site form post carries no token.
    """
    token = DeviceToken.authenticate(_bearer_token(request))
    if token is None:
        response = _api_error("Invalid or missing device token.", 401)
        response["WWW-Authenticate"] = "Bearer"
        return response

    patient = token.patient
    if not patient.is_approved or patient.is_rejected:
        return _api_error("This account is not active.", 403)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _api_error("Request body must be UTF-8 JSON.", 400)

    if not isinstance(payload, dict) or not isinstance(
        payload.get("readings"), list
    ):
        return _api_error('Expected an object with a "readings" list.', 400)

    rows = payload["readings"]
    if not rows:
        return _api_error("No readings supplied.", 400)
    if len(rows) > MAX_API_READINGS:
        return _api_error(
            f"At most {MAX_API_READINGS} readings per request.", 400
        )

    parsed, errors = [], []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"Reading {index}: must be an object.")
            continue
        try:
            parsed.append(parse_reading_row(row))
        except ValueError as exc:
            errors.append(f"Reading {index}: {exc}")

    # All-or-nothing, matching the CSV importer: a device retrying a batch
    # should not have to reason about which rows already landed.
    if errors:
        return _api_error("Some readings were invalid.", 400, details=errors[:10])

    with transaction.atomic():
        created = HealthReading.objects.bulk_create(
            HealthReading(patient=patient, source=ReadingSource.DEVICE, **row)
            for row in parsed
        )
        token.mark_used()

    return JsonResponse({"created": len(created)}, status=201)
