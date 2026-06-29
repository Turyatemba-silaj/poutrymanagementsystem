from django.db import migrations, models


def normalize_flock_remarks(apps, schema_editor):
    Flock = apps.get_model('PoutryManagementSysyem', 'Flock')
    for flock in Flock.objects.all():
        if flock.remarks == 'Active':
            flock.remarks = 'Available'
        elif flock.remarks in {'Sold', 'Depleted'}:
            flock.remarks = 'Died'
        flock.save(update_fields=['remarks'])


class Migration(migrations.Migration):

    dependencies = [
        ('PoutryManagementSysyem', '0004_alter_flock_breed'),
    ]

    operations = [
        migrations.RenameField(
            model_name='flock',
            old_name='status',
            new_name='remarks',
        ),
        migrations.AlterField(
            model_name='flock',
            name='remarks',
            field=models.CharField(choices=[('Available', 'Available'), ('Died', 'Died'), ('Sick', 'Sick')], default='Available', max_length=20),
        ),
        migrations.RunPython(normalize_flock_remarks, migrations.RunPython.noop),
    ]
