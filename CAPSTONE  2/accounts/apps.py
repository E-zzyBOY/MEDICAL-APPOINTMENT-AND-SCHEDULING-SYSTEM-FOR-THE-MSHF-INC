import sys

from django.apps import AppConfig


def _patch_template_context_copy_for_py313():
    """Django 4.2 officially supports Python only up to 3.12. On 3.13+ its
    BaseContext.__copy__ still uses copy(super()), which those Pythons no
    longer allow, so anything that copies a template context — the Django
    admin changelist (/django-admin/accounts/customuser/), the test client's
    template instrumentation — crashes with "AttributeError: 'super' object
    has no attribute 'dicts'". This applies the fix Django 5.x shipped.
    Remove after upgrading to Django >= 5."""
    if sys.version_info < (3, 13):
        return
    from django.template.context import BaseContext

    def _base_context_copy(self):
        duplicate = self.__class__.__new__(self.__class__)
        duplicate.__dict__ = self.__dict__.copy()
        duplicate.dicts = self.dicts[:]
        return duplicate

    BaseContext.__copy__ = _base_context_copy


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        _patch_template_context_copy_for_py313()
