from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DetailView, ListView

from apps.accounts.mixins import (
    AssignedPatientMixin,
    DepartmentRequiredMixin,
    DoctorRequiredMixin,
)

from .forms import ServiceOrderForm
from .models import OrderStatus, ServiceOrder


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
