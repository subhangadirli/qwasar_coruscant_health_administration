from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.accounts.models import Role


class DepartmentKind(models.TextChoices):
    CT = "ct", "CT scan"
    PET = "pet", "PET scan"
    MRI = "mri", "MRI"
    XRAY = "xray", "X-ray"
    LAB = "lab", "Laboratory"
    OTHER = "other", "Other"


class Department(models.Model):
    """A service that executes orders, such as imaging or the lab."""

    name = models.CharField(max_length=100, unique=True)
    kind = models.CharField(
        max_length=16, choices=DepartmentKind.choices, default=DepartmentKind.OTHER
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive departments stop appearing on the order form.",
    )
    staff = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="departments",
        limit_choices_to={"role": Role.DEPARTMENT},
        help_text="Department accounts that work this queue.",
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"


class OrderStatus(models.TextChoices):
    ORDERED = "ordered", "Ordered"
    IN_PROGRESS = "in_progress", "In progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class OrderPriority(models.TextChoices):
    ROUTINE = "routine", "Routine"
    URGENT = "urgent", "Urgent"


# Statuses a department still has work to do on.
OPEN_STATUSES = (OrderStatus.ORDERED, OrderStatus.IN_PROGRESS)


class ServiceOrderQuerySet(models.QuerySet):
    def open(self):
        return self.filter(status__in=OPEN_STATUSES)

    def closed(self):
        return self.exclude(status__in=OPEN_STATUSES)


class ServiceOrder(models.Model):
    """A doctor's request for a department to perform a procedure.

    The lifecycle is ordered -> in progress -> completed, with cancellation
    available only until a department starts work. Execution and result
    upload are the department's side of this (M4); what lives here is what
    the doctor placing the order needs, plus the transitions the queue will
    drive so the rules live with the model rather than in a view.
    """

    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="service_orders",
        limit_choices_to={"role": Role.PATIENT},
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        # An order is part of the patient's record, so it outlives the
        # ordering doctor's account.
        on_delete=models.PROTECT,
        related_name="placed_orders",
        limit_choices_to={"role": Role.DOCTOR},
    )
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="orders"
    )
    procedure = models.CharField(
        max_length=120,
        help_text="What to perform, for example 'CT head without contrast'.",
    )
    notes = models.TextField(
        blank=True, help_text="Clinical context for the department."
    )
    priority = models.CharField(
        max_length=16,
        choices=OrderPriority.choices,
        default=OrderPriority.ROUTINE,
    )
    status = models.CharField(
        max_length=16, choices=OrderStatus.choices, default=OrderStatus.ORDERED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = ServiceOrderQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["department", "status", "-created_at"]),
            models.Index(fields=["patient", "-created_at"]),
        ]

    @property
    def is_open(self):
        return self.status in OPEN_STATUSES

    @property
    def can_cancel(self):
        """Cancellable until a department has started work on it."""
        return self.status == OrderStatus.ORDERED

    def cancel(self):
        if not self.can_cancel:
            raise ValueError("Only an unstarted order can be cancelled.")
        self.status = OrderStatus.CANCELLED
        self.save(update_fields=["status", "updated_at"])

    def start(self):
        if self.status != OrderStatus.ORDERED:
            raise ValueError("Only a newly placed order can be started.")
        self.status = OrderStatus.IN_PROGRESS
        self.save(update_fields=["status", "updated_at"])

    def complete(self, when=None):
        if not self.is_open:
            raise ValueError("Only an open order can be completed.")
        self.status = OrderStatus.COMPLETED
        self.completed_at = when or timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])

    def __str__(self):
        return f"{self.procedure} for {self.patient.username}"
