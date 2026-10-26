from django.db import migrations

from tracker.profesia import profesia_offer_id


def backfill(apps, schema_editor):
    # Hand-entered Profesia vacancies saved before Vacancy.save() learned to
    # read the offer id from the link. Historical models have no custom save().
    Vacancy = apps.get_model("tracker", "Vacancy")
    taken = set(
        Vacancy.objects.filter(external_id__isnull=False).values_list("owner_id", "external_id")
    )
    for vacancy in Vacancy.objects.filter(external_id__isnull=True).exclude(url="").order_by("pk"):
        offer_id = profesia_offer_id(vacancy.url)
        if offer_id is None or (vacancy.owner_id, offer_id) in taken:
            continue
        taken.add((vacancy.owner_id, offer_id))
        vacancy.external_id = offer_id
        vacancy.save(update_fields=["external_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0008_vacancy_closed_at"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
