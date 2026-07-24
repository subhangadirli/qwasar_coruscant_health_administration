from django import forms

from .models import Department, ServiceOrder


class ServiceOrderForm(forms.ModelForm):
    """A doctor placing an order.

    ``patient``, ``doctor`` and ``status`` are absent on purpose: the first
    two come from the URL and the session, and a new order always starts as
    placed rather than at a status the submitter chose.
    """

    class Meta:
        model = ServiceOrder
        fields = ("department", "procedure", "priority", "notes")
        widgets = {"notes": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A retired department should not collect new work.
        self.fields["department"].queryset = Department.objects.filter(
            is_active=True
        )
