import io
import os
from datetime import datetime

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        'Dumps the database (same flags as the manual migration-runbook backup) and '
        'uploads it to Cloudinary as a raw file, since Render\'s disk is ephemeral. '
        'Falls back to writing a local backups/ directory when CLOUDINARY_URL is unset '
        '(local dev has no ephemeral-disk problem to work around).'
    )

    def handle(self, *args, **options):
        buffer = io.StringIO()
        call_command(
            'dumpdata',
            '--natural-foreign', '--natural-primary',
            '-e', 'contenttypes', '-e', 'auth.permission',
            '-e', 'admin.logentry', '-e', 'sessions.session',
            stdout=buffer,
        )
        content = buffer.getvalue()
        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M')
        filename = f'backup_{timestamp}.json'

        if os.environ.get('CLOUDINARY_URL'):
            import cloudinary.uploader
            result = cloudinary.uploader.upload(
                io.BytesIO(content.encode('utf-8')),
                resource_type='raw',
                public_id=f'backups/{filename}',
                overwrite=False,
            )
            self.stdout.write(self.style.SUCCESS(
                f'Backup uploaded to Cloudinary: {result.get("secure_url", result.get("url"))}'
            ))
        else:
            backups_dir = settings.BASE_DIR / 'backups'
            backups_dir.mkdir(exist_ok=True)
            path = backups_dir / filename
            path.write_text(content, encoding='utf-8')
            self.stdout.write(self.style.SUCCESS(f'Backup written locally to {path}'))
