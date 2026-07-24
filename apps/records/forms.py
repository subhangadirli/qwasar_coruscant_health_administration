import csv
import io

from django import forms

from .ingest import parse_reading_row
from .models import HealthReading, ReadingSource, Report

CSV_REQUIRED_COLUMNS = {"metric", "value", "recorded_at"}
MAX_CSV_BYTES = 1024 * 1024
MAX_CSV_ROWS = 1000


class HealthReadingForm(forms.ModelForm):
    """Manual single-reading entry.

    ``patient`` is deliberately absent: the view sets it from the logged-in
    user so a submitted field can never file a reading against someone else.
    Future-dated readings are rejected by HealthReading.clean().
    """

    class Meta:
        model = HealthReading
        fields = ("metric", "value", "unit", "recorded_at")
        widgets = {
            "recorded_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }
        help_texts = {"unit": "Leave blank to use the standard unit."}


class ReportForm(forms.ModelForm):
    """A doctor writing a report or prescription.

    ``patient``, ``doctor`` and ``status`` are absent on purpose: the first
    two come from the URL and the session so a submitted field cannot file
    a report against another patient or under another doctor's name, and
    publishing is a separate deliberate action.
    """

    class Meta:
        model = Report
        fields = ("kind", "title", "body")
        widgets = {"body": forms.Textarea(attrs={"rows": 12})}
        labels = {"kind": "Type"}
        help_texts = {
            "body": "Saved as a draft; the patient sees it only once published.",
        }


class ReadingCSVUploadForm(forms.Form):
    """Bulk import of a device CSV export.

    Expected header: ``metric,value,recorded_at`` plus an optional ``unit``.
    The whole file is rejected if any row is bad, so a failed import never
    leaves a patient with a half-loaded history.
    """

    csv_file = forms.FileField(
        label="Device CSV export",
        help_text="Columns: metric, value, recorded_at, and optionally unit.",
    )

    def clean_csv_file(self):
        upload = self.cleaned_data["csv_file"]
        if upload.size > MAX_CSV_BYTES:
            raise forms.ValidationError("File is larger than 1 MB.")
        try:
            text = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise forms.ValidationError("File must be UTF-8 encoded text.")
        self.parsed_rows = self._parse(text)
        return upload

    def _parse(self, text):
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise forms.ValidationError("File is empty.")

        header = {name.strip().lower() for name in reader.fieldnames if name}
        missing = CSV_REQUIRED_COLUMNS - header
        if missing:
            raise forms.ValidationError(
                "Missing required column(s): %s." % ", ".join(sorted(missing))
            )

        rows, errors = [], []
        for number, raw in enumerate(reader, start=2):  # row 1 is the header
            if len(rows) >= MAX_CSV_ROWS:
                errors.append(
                    f"More than {MAX_CSV_ROWS} rows; please split the file."
                )
                break
            try:
                rows.append(self._parse_row(raw))
            except ValueError as exc:
                errors.append(f"Row {number}: {exc}")

        if errors:
            raise forms.ValidationError(errors[:10])
        if not rows:
            raise forms.ValidationError("File contains no data rows.")
        return rows

    @staticmethod
    def _parse_row(raw):
        cleaned = {}
        for key, value in raw.items():
            if key is None:  # surplus columns land under a None key
                continue
            if isinstance(value, list):
                value = ""
            cleaned[key.strip().lower()] = (value or "").strip()
        return parse_reading_row(cleaned)

    def save(self, patient):
        return HealthReading.objects.bulk_create(
            HealthReading(patient=patient, source=ReadingSource.CSV, **row)
            for row in self.parsed_rows
        )
