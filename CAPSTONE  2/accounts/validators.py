import re
from django.core.exceptions import ValidationError

# Accepts Philippine mobile numbers in the two formats people actually type:
#   09XXXXXXXXX        (11 digits, local format)
#   +639XXXXXXXXX       (country code format)
# Spaces and hyphens are stripped before checking, so "0917 123 4567" and
# "0917-123-4567" are both accepted alongside the unspaced form.
_PH_MOBILE_RE = re.compile(r'^(09\d{9}|\+639\d{9})$')


def validate_ph_mobile_number(value):
    """Raises ValidationError unless value is a valid PH mobile number."""
    cleaned = re.sub(r'[\s-]', '', value or '')
    if not _PH_MOBILE_RE.match(cleaned):
        raise ValidationError(
            'Enter a valid mobile number, e.g. 09171234567 or +639171234567.',
            code='invalid_mobile_number',
        )


def normalize_ph_mobile_number(value):
    """Strips spaces/hyphens for storage; assumes value already passed
    validate_ph_mobile_number."""
    return re.sub(r'[\s-]', '', value or '')
