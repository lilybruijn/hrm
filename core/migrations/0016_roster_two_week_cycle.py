from django.db import migrations, models
from decimal import Decimal

def forwards(apps, schema_editor):
    Roster = apps.get_model("core", "Roster")
    for r in Roster.objects.all():
        # cycle start default = start_date
        if not r.cycle_start_date:
            r.cycle_start_date = r.start_date

        # kopieer oude week naar zowel A als B (zodat niets "verdwijnt")
        r.mon_a_hours = getattr(r, "mon_hours", Decimal("0"))
        r.tue_a_hours = getattr(r, "tue_hours", Decimal("0"))
        r.wed_a_hours = getattr(r, "wed_hours", Decimal("0"))
        r.thu_a_hours = getattr(r, "thu_hours", Decimal("0"))
        r.fri_a_hours = getattr(r, "fri_hours", Decimal("0"))
        r.sat_a_hours = getattr(r, "sat_hours", Decimal("0"))
        r.sun_a_hours = getattr(r, "sun_hours", Decimal("0"))

        r.mon_b_hours = r.mon_a_hours
        r.tue_b_hours = r.tue_a_hours
        r.wed_b_hours = r.wed_a_hours
        r.thu_b_hours = r.thu_a_hours
        r.fri_b_hours = r.fri_a_hours
        r.sat_b_hours = r.sat_a_hours
        r.sun_b_hours = r.sun_a_hours

        r.save()

def backwards(apps, schema_editor):
    # (optioneel) terugkopiëren zou kunnen, maar meestal niet nodig
    pass

class Migration(migrations.Migration):
    dependencies = [
        ("core", "0015_roster_workpackage_rosterday_rosterdaywork"),
    ]

    operations = [
       

   
    ]
