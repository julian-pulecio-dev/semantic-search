from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("document", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="embedding_batches_total",
            field=models.PositiveIntegerField(
                blank=True, default=None, null=True
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="embedding_batches_done",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
