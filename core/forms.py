from django import forms
from django.utils import timezone

from .models import Signal, Person, SignalHistory, StudentProfile, EmployeeProfile, Organization, ContactPerson, BenefitType, Location, WorkPackage
from django.contrib.auth import get_user_model


class SignalForm(forms.ModelForm):
    class Meta:
        model = Signal
        fields = ["category", "title", "body", "active_from", "assigned_to", "notify"]
        widgets = {
            "active_from": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # nice labels
        self.fields["category"].label = "Onderdeel"
        self.fields["title"].label = "Titel"
        self.fields["body"].label = "Melding"
        self.fields["active_from"].label = "Geldig vanaf"
        self.fields["assigned_to"].label = "Toegewezen aan"
        self.fields["notify"].label = "Notificatie sturen"

        
        User = get_user_model()
        self.fields["assigned_to"].queryset = User.objects.filter(username__in=["admin", "emma"]).order_by("username")



        # default: now (rounded)
        if not self.initial.get("active_from"):
            now = timezone.localtime(timezone.now()).replace(second=0, microsecond=0)
            # datetime-local expects "YYYY-MM-DDTHH:MM"
            self.initial["active_from"] = now.strftime("%Y-%m-%dT%H:%M")


class SignalCreateFromListForm(forms.ModelForm):
    person = forms.ModelChoiceField(
        queryset=Person.objects.filter(person_type="student").order_by("last_name", "first_name"),
        label="Student",
    )

    class Meta:
        model = Signal
        fields = ["person", "category", "title", "body", "active_from", "assigned_to", "notify"]
        widgets = {
            "active_from": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["category"].label = "Onderdeel"
        self.fields["title"].label = "Titel"
        self.fields["body"].label = "Melding"
        self.fields["active_from"].label = "Geldig vanaf"
        self.fields["assigned_to"].label = "Toegewezen aan"
        self.fields["notify"].label = "Notificatie sturen"

        now = timezone.localtime(timezone.now()).replace(second=0, microsecond=0)
        self.initial.setdefault("active_from", now.strftime("%Y-%m-%dT%H:%M"))




class PersonBaseForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = [
            "first_name","last_name","birth_date","email","phone",
            "address_line","postal_code","city","bsn","iban","notes"
        ]

class StudentCreateForm(PersonBaseForm):
    # student-profile velden erbij (minimaal, later uitbreiden)
    status = forms.ChoiceField(choices=StudentProfile.STATUS_CHOICES)
    start_date = forms.DateField(required=False)

class EmployeeCreateForm(PersonBaseForm):
    hired_date = forms.DateField(required=False)
    job_title = forms.CharField(required=False)


class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ["organization_type", "name"]
        widgets = {
            "organization_type": forms.Select(attrs={"style": "width:100%;"}),
            "name": forms.TextInput(attrs={"style": "width:100%;"}),
        }


class ContactPersonForm(forms.ModelForm):
    class Meta:
        model = ContactPerson
        fields = ["organization", "name", "email", "phone", "notes"]
        widgets = {
            "organization": forms.Select(attrs={"style": "width:100%;"}),
            "name": forms.TextInput(attrs={"style": "width:100%;"}),
            "email": forms.EmailInput(attrs={"style": "width:100%;"}),
            "phone": forms.TextInput(attrs={"style": "width:100%;"}),
            "notes": forms.Textarea(attrs={"style": "width:100%;", "rows": 4}),
        }


class BenefitTypeForm(forms.ModelForm):
    class Meta:
        model = BenefitType
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={"style": "width:100%;"}),
        }


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={"style": "width:100%;"}),
        }

class WorkPackageForm(forms.ModelForm):
    class Meta:
        model = WorkPackage
        fields = ["code", "title", "parent", "sort_order"]
        widgets = {
            "code": forms.TextInput(attrs={"style": "width:100%;"}),
            "title": forms.TextInput(attrs={"style": "width:100%;"}),
            "parent": forms.Select(attrs={"style": "width:100%;"}),
            "sort_order": forms.NumberInput(attrs={"style": "width:100%;"}),
        }