from django.db import migrations


def mark_existing_verified(apps, schema_editor):
    """Accounts that predate the email-verification feature were already
    using the app; gating them retroactively would lock out every real
    patient (and staff) on the next deploy."""
    CustomUser = apps.get_model('accounts', 'CustomUser')
    CustomUser.objects.update(email_verified=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_customuser_email_verified'),
    ]

    operations = [
        migrations.RunPython(mark_existing_verified, noop),
    ]
