from django.views.generic import ListView

from apps.accounts.mixins import RoleRequiredMixin
from apps.accounts.models import Role

from .models import MetricType


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
