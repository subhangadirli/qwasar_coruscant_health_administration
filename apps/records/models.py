from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.accounts.models import Role


class MetricType(models.TextChoices):
    HEART_RATE = "heart_rate", "Heart rate"
    BP_SYSTOLIC = "bp_systolic", "Blood pressure (systolic)"
    BP_DIASTOLIC = "bp_diastolic", "Blood pressure (diastolic)"
    BLOOD_GLUCOSE = "blood_glucose", "Blood glucose"
    TEMPERATURE = "temperature", "Body temperature"
    SPO2 = "spo2", "Oxygen saturation"
    WEIGHT = "weight", "Weight"


# Canonical unit for each metric, applied when an upload omits one so that
# readings of the same metric stay comparable on a trend chart.
DEFAULT_UNITS = {
    MetricType.HEART_RATE: "bpm",
    MetricType.BP_SYSTOLIC: "mmHg",
    MetricType.BP_DIASTOLIC: "mmHg",
    MetricType.BLOOD_GLUCOSE: "mg/dL",
    MetricType.TEMPERATURE: "C",
    MetricType.SPO2: "%",
    MetricType.WEIGHT: "kg",
}


class ReadingSource(models.TextChoices):
    MANUAL = "manual", "Manual entry"
    CSV = "csv", "CSV upload"
    DEVICE = "device", "Device API"


class HealthReading(models.Model):
    """A single time-series datapoint uploaded for a patient.

    Readings arrive from a wearable/home device (API or CSV export) or are
    entered by hand. They are the input to the improvement/worsening trend
    analysis a doctor sees.
    """

    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="health_readings",
        limit_choices_to={"role": Role.PATIENT},
    )
    metric = models.CharField(max_length=32, choices=MetricType.choices)
    value = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    unit = models.CharField(max_length=16, blank=True)
    recorded_at = models.DateTimeField(
        help_text="When the device took the reading."
    )
    source = models.CharField(
        max_length=16,
        choices=ReadingSource.choices,
        default=ReadingSource.MANUAL,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-recorded_at",)
        indexes = [
            models.Index(fields=["patient", "metric", "-recorded_at"]),
        ]

    def clean(self):
        if self.recorded_at and self.recorded_at > timezone.now():
            raise ValidationError(
                {"recorded_at": "A reading cannot be recorded in the future."}
            )

    def save(self, *args, **kwargs):
        if not self.unit:
            self.unit = DEFAULT_UNITS.get(self.metric, "")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_metric_display()}: {self.value} {self.unit}"
