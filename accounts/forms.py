from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, CandidateProfile, EmployerProfile


class RegisterForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        help_text="Required. Must be unique.",
    )

    class Meta:
        model = User
        fields = ("username", "email", "role", "password1", "password2")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with that email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user
    
class CandidateProfileForm(forms.ModelForm):
    skills = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Python, SQL, Rust"}),
        help_text="Comma-separated. Example: Python, SQL, Rust",
    )

    class Meta:
        model = CandidateProfile
        fields = ("display_name", "skills", "resume_text")
        widgets = {"resume_text": forms.Textarea(attrs={"rows": 10})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-fill the input with a comma-separated string when editing
        skills = self.instance.skills if self.instance else []
        if isinstance(skills, list):
            self.initial["skills"] = ", ".join(skills)

    def clean_skills(self):
        raw = self.cleaned_data.get("skills") or ""
        return [p.strip() for p in raw.split(",") if p.strip()]

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.skills = self.cleaned_data["skills"]
        if commit:
            instance.save()
        return instance


class EmployerProfileForm(forms.ModelForm):
    class Meta:
        model = EmployerProfile
        fields = ("company_name", "description")
        widgets = {"description": forms.Textarea(attrs={"rows": 10})}