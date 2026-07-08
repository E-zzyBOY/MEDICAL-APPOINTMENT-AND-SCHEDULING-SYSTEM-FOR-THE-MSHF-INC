from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0007_appointmentpatientdetails_relationship'),
    ]

    operations = [
        migrations.AlterField(
            model_name='appointment',
            name='status',
            field=models.CharField(choices=[('Pending Assignment', 'Pending Assignment'), ('Scheduled', 'Scheduled'), ('Confirmed', 'Confirmed'), ('Completed', 'Completed'), ('Cancelled', 'Cancelled'), ('No-Show', 'No-Show'), ('Rescheduled', 'Rescheduled'), ('Pending Reschedule', 'Pending Reschedule')], default='Pending Assignment', max_length=30),
        ),
    ]
