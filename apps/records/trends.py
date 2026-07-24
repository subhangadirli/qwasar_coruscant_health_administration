"""Improvement/worsening analysis over a patient's health readings.

A doctor needs to know whether a patient is getting better, not just what
the last number was. The rule here is deliberately simple and explainable:
compare the mean of the most recent readings against the mean of the block
before it, and ask whether that mean moved *toward* or *away from* the
metric's healthy reference range.

Working from distance-to-range rather than raw direction is what makes the
answer meaningful per metric. A falling heart rate is an improvement at 110
bpm and a deterioration at 55; the same arithmetic covers both without any
per-metric special-casing.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.db import models

from .models import MetricType

# Adult reference ranges, used only to decide which direction is better.
# These are not diagnostic thresholds; the doctor reads the numbers.
TARGET_RANGES = {
    MetricType.HEART_RATE: (Decimal("60"), Decimal("100")),
    MetricType.BP_SYSTOLIC: (Decimal("90"), Decimal("120")),
    MetricType.BP_DIASTOLIC: (Decimal("60"), Decimal("80")),
    MetricType.BLOOD_GLUCOSE: (Decimal("70"), Decimal("140")),
    MetricType.TEMPERATURE: (Decimal("36.1"), Decimal("37.5")),
    MetricType.SPO2: (Decimal("95"), Decimal("100")),
    # Weight has no population-wide healthy range, so a change in it is
    # reported without being called good or bad.
    MetricType.WEIGHT: None,
}

# Readings per comparison window, and the minimum needed to compare at all.
WINDOW = 5
MIN_READINGS = 4

# A move smaller than this fraction of the healthy band's width is noise.
NOISE_FRACTION = Decimal("0.05")


class TrendStatus(models.TextChoices):
    IMPROVING = "improving", "Improving"
    WORSENING = "worsening", "Worsening"
    STABLE = "stable", "Stable"
    UNCLEAR = "unclear", "No reference range"
    INSUFFICIENT = "insufficient", "Not enough data"


class TrendDirection(models.TextChoices):
    UP = "up", "Rising"
    DOWN = "down", "Falling"
    FLAT = "flat", "Level"


@dataclass(frozen=True)
class Trend:
    """One metric's verdict, ready to render."""

    metric: str
    status: str
    direction: str
    sample_size: int
    unit: str = ""
    baseline_mean: Decimal = None
    recent_mean: Decimal = None
    change: Decimal = None

    @property
    def label(self):
        return MetricType(self.metric).label

    @property
    def status_label(self):
        return TrendStatus(self.status).label

    @property
    def direction_label(self):
        return TrendDirection(self.direction).label

    @property
    def is_comparable(self):
        """True when two windows were actually compared."""
        return self.status != TrendStatus.INSUFFICIENT


def _mean(values):
    return (sum(values, Decimal("0")) / len(values)).quantize(Decimal("0.01"))


def _deviation(value, bounds):
    """How far a value sits outside its healthy range (0 when inside)."""
    low, high = bounds
    if value < low:
        return low - value
    if value > high:
        return value - high
    return Decimal("0")


def analyse(readings, metric=None, window=WINDOW):
    """Summarise a single metric from readings ordered newest first.

    The two windows are kept the same size so a long history is never
    compared against a single stray datapoint.
    """
    readings = list(readings)
    metric = metric or (readings[0].metric if readings else None)
    unit = readings[0].unit if readings else ""

    if len(readings) < MIN_READINGS:
        return Trend(
            metric=metric,
            status=TrendStatus.INSUFFICIENT,
            direction=TrendDirection.FLAT,
            sample_size=len(readings),
            unit=unit,
        )

    size = min(window, len(readings) // 2)
    recent_mean = _mean([r.value for r in readings[:size]])
    baseline_mean = _mean([r.value for r in readings[size : size * 2]])
    change = recent_mean - baseline_mean

    if change > 0:
        direction = TrendDirection.UP
    elif change < 0:
        direction = TrendDirection.DOWN
    else:
        direction = TrendDirection.FLAT

    bounds = TARGET_RANGES.get(metric)
    if bounds is None:
        status = TrendStatus.UNCLEAR
    else:
        low, high = bounds
        tolerance = (high - low) * NOISE_FRACTION
        drift = _deviation(recent_mean, bounds) - _deviation(baseline_mean, bounds)
        if abs(drift) < tolerance:
            status = TrendStatus.STABLE
        elif drift < 0:
            status = TrendStatus.IMPROVING
        else:
            status = TrendStatus.WORSENING

    return Trend(
        metric=metric,
        status=status,
        direction=direction,
        sample_size=size * 2,
        unit=unit,
        baseline_mean=baseline_mean,
        recent_mean=recent_mean,
        change=change,
    )


def summarise_patient(patient, window=WINDOW):
    """A Trend per metric the patient has any readings for.

    Metrics with no readings are left out entirely rather than shown as
    empty rows, so the summary is a list of what is actually being tracked.
    """
    trends = []
    for metric in MetricType.values:
        readings = list(
            patient.health_readings.filter(metric=metric)[: window * 2]
        )
        if readings:
            trends.append(analyse(readings, metric=metric, window=window))
    return trends
