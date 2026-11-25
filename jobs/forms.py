from django import forms
from .models import Job
from datetime import timedelta
from django.utils import timezone
from .models import Slot


class JobForm(forms.ModelForm):
    required_skills = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Python, SQL"}),
        help_text="Comma-separated. Leave empty for a job requiring no specific skills.",
    )

    class Meta:
        model = Job
        fields = ("title", "description", "required_skills")
        widgets = {"description": forms.Textarea(attrs={"rows": 8})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and isinstance(self.instance.required_skills, list):
            self.initial["required_skills"] = ", ".join(self.instance.required_skills)

    def clean_required_skills(self):
        raw = self.cleaned_data.get("required_skills") or ""
        return [p.strip() for p in raw.split(",") if p.strip()]

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.required_skills = self.cleaned_data["required_skills"]
        if commit:
            instance.save()
        return instance
    
class SlotForm(forms.ModelForm):
    class Meta:
        model = Slot
        fields = ("start_time",)
        widgets = {
            "start_time": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        self.employer = kwargs.pop("employer", None)
        super().__init__(*args, **kwargs)
        self.fields["start_time"].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean_start_time(self):
        start = self.cleaned_data["start_time"]
        if start <= timezone.now():
            raise forms.ValidationError("Slot must be in the future.")
        
        if self.employer is not None:
            end = start + timedelta(minutes=30)
            overlaps = Slot.objects.filter(
                employer=self.employer,
                start_time__lt=end,
                end_time__gt=start,
            ).exists()
            if overlaps:
                raise forms.ValidationError(
                    "This time overlaps with a slot you already created."
                )
        return start

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.end_time = instance.start_time + timedelta(minutes=30)
        if commit:
            instance.save()
        return instance