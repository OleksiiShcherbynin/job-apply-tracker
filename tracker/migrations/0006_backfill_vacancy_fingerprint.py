from django.db import migrations

from tracker.fingerprints import fingerprint


def backfill(apps, schema_editor):
    # Historical models have no custom save(), so compute the value here.
    Vacancy = apps.get_model("tracker", "Vacancy")
    for vacancy in Vacancy.objects.select_related("company"):
        vacancy.fingerprint = fingerprint(vacancy.company.name, vacancy.title)
        vacancy.save(update_fields=["fingerprint"])


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0005_vacancy_fingerprint_vacancy_first_seen_at_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
