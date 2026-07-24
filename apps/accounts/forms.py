from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Role, User

# Roles that may self-register through the public sign-up form. Admin,
# department, and emergency accounts are provisioned by an administrator.
SELF_REGISTER_ROLES = [
    (Role.PATIENT.value, Role.PATIENT.label),
    (Role.DOCTOR.value, Role.DOCTOR.label),
]


class RegistrationForm(UserCreationForm):
    """Public sign-up for patients and doctors.

    New accounts are created unapproved and must be acknowledged by an
    administrator before they can reach their dashboard.
    """

    email = forms.EmailField(required=True)
    role = forms.ChoiceField(choices=SELF_REGISTER_ROLES)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "role", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.role = self.cleaned_data["role"]
        user.is_approved = False
        if commit:
            user.save()
        return user
