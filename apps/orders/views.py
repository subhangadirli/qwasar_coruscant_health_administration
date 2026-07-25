from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DetailView, ListView

from apps.accounts.mixins import (
    AssignedPatientMixin,
    DepartmentRequiredMixin,
    DoctorRequiredMixin,
    RoleRequiredMixin,
)
from apps.accounts.models import Role

from .forms import OrderResultForm, ServiceOrderForm
from .models import OrderResult, OrderStatus, ServiceOrder


class DoctorOrdersMixin(DoctorRequiredMixin):
    """Restrict orders to the ones this doctor placed."""

    def get_queryset(self):
        return self.request.user.placed_orders.select_related(
            "patient", "department"
        )


class DoctorOrdersView(DoctorOrdersMixin, ListView):
    """Orders this doctor placed, open ones first by default."""

    template_name = "orders/order_list.html"
    context_object_name = "orders"
    paginate_by = 25

    def get_scope(self):
        scope = self.request.GET.get("scope")
        return scope if scope in {"open", "closed"} else "open"

    def get_queryset(self):
        queryset = super().get_queryset()
        return (
            queryset.open() if self.get_scope() == "open" else queryset.closed()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["scope"] = self.get_scope()
        return context


class OrderDetailView(DoctorOrdersMixin, DetailView):
    template_name = "orders/order_detail.html"
    context_object_name = "order"


class PlaceOrderView(AssignedPatientMixin, CreateView):
    """Order a service for an assigned patient."""

    form_class = ServiceOrderForm
    template_name = "orders/order_form.html"

    def form_valid(self, form):
        form.instance.patient = self.get_patient()
        form.instance.doctor = self.request.user
        messages.success(self.request, "Order placed.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["patient"] = self.get_patient()
        return context

    def get_success_url(self):
        return reverse("orders:order_detail", args=[self.object.pk])


class DepartmentQueueMixin(DepartmentRequiredMixin):
    """Restrict orders to the ones this department account works."""

    def get_queryset(self):
        return ServiceOrder.objects.for_departments_of(
            self.request.user
        ).select_related("patient", "department", "doctor")


class DepartmentQueueView(DepartmentQueueMixin, ListView):
    """The queue of orders addressed to this account's department(s)."""

    template_name = "orders/department_queue.html"
    context_object_name = "orders"
    paginate_by = 25

    def get_scope(self):
        scope = self.request.GET.get("scope")
        return scope if scope in {"open", "closed"} else "open"

    def get_queryset(self):
        queryset = super().get_queryset()
        return (
            queryset.open() if self.get_scope() == "open" else queryset.closed()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["scope"] = self.get_scope()
        return context


class DepartmentOrderDetailView(DepartmentQueueMixin, DetailView):
    template_name = "orders/department_order_detail.html"
    context_object_name = "order"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Offer the result form only while the order is being worked.
        if self.object.status == OrderStatus.IN_PROGRESS:
            context.setdefault("form", OrderResultForm())
        return context


class StartOrderView(DepartmentQueueMixin, View):
    """Accept a queued order into progress."""

    def post(self, request, pk):
        order = get_object_or_404(self.get_queryset(), pk=pk)
        try:
            order.start()
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Started {order.procedure}.")
        return redirect("orders:department_order", pk=order.pk)


class CompleteOrderView(DepartmentQueueMixin, View):
    """Record a result and mark the order completed."""

    def post(self, request, pk):
        order = get_object_or_404(self.get_queryset(), pk=pk)
        if order.status != OrderStatus.IN_PROGRESS:
            messages.error(request, "Only an in-progress order can be completed.")
            return redirect("orders:department_order", pk=order.pk)

        form = OrderResultForm(request.POST, request.FILES)
        if not form.is_valid():
            context = self.get_detail_context(order, form)
            return self.render_to_response(context)

        result = form.save(commit=False)
        result.order = order
        result.uploaded_by = request.user
        result.save()
        order.complete()
        messages.success(request, f"Completed {order.procedure}.")
        return redirect("orders:department_order", pk=order.pk)

    def get_detail_context(self, order, form):
        return {"order": order, "form": form}

    def render_to_response(self, context):
        return render(
            self.request, "orders/department_order_detail.html", context
        )


class PatientOrdersMixin(RoleRequiredMixin):
    """Restrict orders to the ones placed for the logged-in patient.

    Scoping the queryset means another patient's order is a 404, never a
    check that runs after the record is fetched.
    """

    allowed_roles = (Role.PATIENT,)

    def get_queryset(self):
        return self.request.user.service_orders.select_related(
            "department", "doctor", "result"
        )


class PatientOrdersView(PatientOrdersMixin, ListView):
    """A patient's own service orders, read-only."""

    template_name = "orders/patient_orders.html"
    context_object_name = "orders"
    paginate_by = 25


class PatientOrderDetailView(PatientOrdersMixin, DetailView):
    template_name = "orders/patient_order_detail.html"
    context_object_name = "order"


class OrderResultDownloadView(LoginRequiredMixin, View):
    """Stream a result's attachment to anyone entitled to the order.

    Serving the file through a permission-checked view (not a public media
    URL) is what keeps results private; M6 swaps the storage for encrypted
    private buckets behind this same check.
    """

    def get(self, request, pk):
        result = get_object_or_404(
            OrderResult.objects.select_related("order", "order__department"), pk=pk
        )
        if not result.attachment:
            raise Http404("This result has no attachment.")
        if not self._may_access(request.user, result.order):
            raise Http404("No such result.")
        return FileResponse(result.attachment.open("rb"), as_attachment=True)

    @staticmethod
    def _may_access(user, order):
        if user == order.patient or user == order.doctor:
            return True
        return order.department.staff.filter(pk=user.pk).exists()


class CancelOrderView(DoctorRequiredMixin, View):
    """Withdraw an order the department has not started yet."""

    def post(self, request, pk):
        order = get_object_or_404(
            request.user.placed_orders.filter(status=OrderStatus.ORDERED),
            pk=pk,
        )
        order.cancel()
        messages.info(request, f"Cancelled {order.procedure}.")
        return redirect("orders:order_detail", pk=order.pk)
