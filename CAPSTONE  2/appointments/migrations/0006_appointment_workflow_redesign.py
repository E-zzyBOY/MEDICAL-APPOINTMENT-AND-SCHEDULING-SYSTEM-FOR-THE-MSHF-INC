from django.db import migrations


class Migration(migrations.Migration):
    """
    Two-part migration:
    1. Data migration: renames all existing 'Pending Time Assignment' records
       to the new 'Pending Assignment' status value.
    2. Schema update: alters the status field choices and default to reflect
       the new workflow statuses ('Pending Assignment' and 'Confirmed').
    """

    dependencies = [
        ('appointments', '0005_alter_appointment_appointment_time_and_more'),
    ]

    def rename_pending_status(apps, schema_editor):
        Appointment = apps.get_model('appointments', 'Appointment')
        Appointment.objects.filter(
            status='Pending Time Assignment'
        ).update(status='Pending Assignment')

    operations = [
        # Step 1: Rename existing data before the schema tightens choices.
        migrations.RunPython(
            rename_pending_status,
            reverse_code=lambda apps, se: apps.get_model(
                'appointments', 'Appointment'
            ).objects.filter(status='Pending Assignment').update(
                status='Pending Time Assignment'
            ),
        ),
        # Step 2: Update choices list and default value on the status field.
        migrations.AlterField(
            model_name='appointment',
            name='status',
            field=__import__('django.db.models', fromlist=['CharField']).CharField(
                choices=[
                    ('Pending Assignment',  'Pending Assignment'),
                    ('Scheduled',           'Scheduled'),
                    ('Confirmed',           'Confirmed'),
                    ('Completed',           'Completed'),
                    ('Cancelled',           'Cancelled'),
                    ('Rescheduled',         'Rescheduled'),
                    ('Pending Reschedule',  'Pending Reschedule'),
                ],
                default='Pending Assignment',
                max_length=30,
            ),
        ),
    ]
