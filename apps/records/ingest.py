"""Validation shared by every reading-upload path (CSV and device API).

Keeping one implementation means the API cannot quietly accept a value the
CSV importer would have rejected.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import DEFAULT_UNITS, MetricType

# DecimalField(max_digits=8, decimal_places=2) tops out just under 1,000,000.
MAX_READING_VALUE = Decimal("1000000")


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, bool):  # bool is an int; never a valid field here
        return str(value)
    return str(value).strip()


def parse_reading_row(row):
    """Validate one incoming reading into model-ready kwargs.

    Accepts already-decoded JSON values as well as CSV strings. Raises
    ValueError with a message naming what was wrong with the row.
    """
    metric = _as_text(row.get("metric"))
    if metric not in MetricType.values:
        raise ValueError(f"unknown metric {metric!r}.")

    raw_value = _as_text(row.get("value"))
    try:
        value = Decimal(raw_value)
    except (InvalidOperation, ValueError):
        raise ValueError(f"value {raw_value!r} is not a number.")
    if not value.is_finite():
        raise ValueError("value must be a finite number.")
    if value < 0:
        raise ValueError("value cannot be negative.")
    if value >= MAX_READING_VALUE:
        raise ValueError("value is out of range.")
    value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    recorded_at = parse_datetime(_as_text(row.get("recorded_at")))
    if recorded_at is None:
        raise ValueError("recorded_at must be an ISO 8601 datetime.")
    if timezone.is_naive(recorded_at):
        recorded_at = timezone.make_aware(recorded_at)
    if recorded_at > timezone.now():
        raise ValueError("recorded_at is in the future.")

    return {
        "metric": metric,
        "value": value,
        "unit": _as_text(row.get("unit")) or DEFAULT_UNITS.get(metric, ""),
        "recorded_at": recorded_at,
    }
