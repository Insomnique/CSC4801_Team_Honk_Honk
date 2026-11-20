from django import forms

from .models import Job


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
            self.fields["required_skills"].initial = ", ".join(self.instance.required_skills)

    def clean_required_skills(self):
        raw = self.cleaned_data.get("required_skills") or ""
        return [p.strip() for p in raw.split(",") if p.strip()]

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.required_skills = self.cleaned_data["required_skills"]
        if commit:
            instance.save()
        return instance