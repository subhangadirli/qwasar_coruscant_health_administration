import json

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)

from apps.accounts.mixins import (
    AssignedPatientMixin,
    DoctorRequiredMixin,
    RoleRequiredMixin,
)
from apps.accounts.models import PatientDoctorAssignment, Role

from .forms import HealthReadingForm, ReadingCSVUploadForm, ReportForm
from .ingest import parse_reading_row
from .models import (
    DeviceToken,
    HealthReading,
    MetricType,
    ReadingSource,
    ReportStatus,
)
from .trends import summarise_patient

# Bounds one device request; matches the spirit of the CSV row cap.
MAX_API_READINGS = 500

# Enough history to show a trend without shipping a huge payload.
CHART_POINT_LIMIT = 100


def valid_metric(value):
    """A metric key from user input, or None if it is not one we know."""
    return value if value in MetricType.values else None


def chart_payload(patient, metric, limit=CHART_POINT_LIMIT):
    """Chart.js-ready series for one metric, or None when there is nothing.

    A chart mixing metrics would put incompatible units on one axis, so a
    series is always a single metric.
    """
    if not metric:
        return None

    readings = list(
        patient.health_readings.filter(metric=metric).order_by("-recorded_at")[
            :limit
        ]
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


class PatientReadingsView(RoleRequiredMixin, ListView):
    """A patient's own health readings, newest first, optionally filtered."""

    allowed_roles = (Role.PATIENT,)
    template_name = "records/reading_list.html"
    context_object_name = "readings"
    paginate_by = 25

    def get_selected_metric(self):
        return valid_metric(self.request.GET.get("metric"))

    def get_chart_metric(self):
        """Metric to plot: the filtered one, else the most recently recorded."""
        selected = self.get_selected_metric()
        if selected:
            return selected
        latest = self.request.user.health_readings.first()
        return latest.metric if latest else None

    def get_chart_data(self):
        return chart_payload(self.request.user, self.get_chart_metric())

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


class DoctorPatientsView(DoctorRequiredMixin, ListView):
    """The doctor's caseload: patients assigned to them."""

    template_name = "records/patient_list.html"
    context_object_name = "patients"
    paginate_by = 25

    def get_queryset(self):
        return (
            PatientDoctorAssignment.patients_of(self.request.user)
            .annotate(
                reading_count=Count("health_readings", distinct=True),
                last_reading_at=Max("health_readings__recorded_at"),
            )
            .order_by("username")
        )


class DoctorPatientDetailView(AssignedPatientMixin, DetailView):
    """One patient's record: trend verdicts, chart, readings, reports."""

    template_name = "records/patient_detail.html"
    context_object_name = "patient"
    reading_limit = 20

    def get_object(self, queryset=None):
        return self.get_patient()

    def get_chart_metric(self):
        selected = valid_metric(self.request.GET.get("metric"))
        if selected:
            return selected
        latest = self.get_patient().health_readings.first()
        return latest.metric if latest else None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        patient = self.get_patient()
        selected = valid_metric(self.request.GET.get("metric"))

        readings = patient.health_readings.all()
        if selected:
            readings = readings.filter(metric=selected)

        context.update(
            {
                "trends": summarise_patient(patient),
                "chart_data": chart_payload(patient, self.get_chart_metric()),
                "metric_choices": MetricType.choices,
                "selected_metric": selected,
                "readings": readings[: self.reading_limit],
                # Published reports from any doctor, plus this doctor's own
                # drafts: a colleague's unfinished draft is not part of the
                # record yet.
                "reports": patient.reports.filter(
                    Q(status=ReportStatus.PUBLISHED) | Q(doctor=self.request.user)
                ).select_related("doctor"),
                # Orders from any doctor: a scan already requested by a
                # colleague is exactly what stops a duplicate being ordered.
                "orders": patient.service_orders.select_related(
                    "department", "doctor"
                ),
            }
        )
        return context


class DoctorReportsMixin(DoctorRequiredMixin):
    """Restrict reports to the ones this doctor wrote."""

    def get_queryset(self):
        return self.request.user.authored_reports.select_related("patient")


class DoctorReportsView(DoctorReportsMixin, ListView):
    template_name = "records/doctor_report_list.html"
    context_object_name = "reports"
    paginate_by = 25


class DoctorReportDetailView(DoctorReportsMixin, DetailView):
    template_name = "records/doctor_report_detail.html"
    context_object_name = "report"


class WriteReportView(AssignedPatientMixin, CreateView):
    """Draft a report or prescription for an assigned patient."""

    form_class = ReportForm
    template_name = "records/report_form.html"

    def form_valid(self, form):
        form.instance.patient = self.get_patient()
        form.instance.doctor = self.request.user
        messages.success(self.request, "Draft saved.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["patient"] = self.get_patient()
        return context

    def get_success_url(self):
        return reverse("records:doctor_report_detail", args=[self.object.pk])


class EditReportView(DoctorReportsMixin, UpdateView):
    """Revise a draft.

    Published reports are deliberately absent from this queryset: once the
    patient can read a report it is part of their record, and correcting it
    means writing a follow-up rather than editing history.
    """

    form_class = ReportForm
    template_name = "records/report_form.html"

    def get_queryset(self):
        return super().get_queryset().filter(status=ReportStatus.DRAFT)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["patient"] = self.object.patient
        return context

    def form_valid(self, form):
        messages.success(self.request, "Draft updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("records:doctor_report_detail", args=[self.object.pk])


class PublishReportView(DoctorRequiredMixin, View):
    """Release a draft to the patient."""

    def post(self, request, pk):
        report = get_object_or_404(
            request.user.authored_reports.filter(status=ReportStatus.DRAFT),
            pk=pk,
        )
        report.publish()
        messages.success(
            request, f"Published to {report.patient.username}."
        )
        return redirect("records:doctor_report_detail", pk=report.pk)


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
