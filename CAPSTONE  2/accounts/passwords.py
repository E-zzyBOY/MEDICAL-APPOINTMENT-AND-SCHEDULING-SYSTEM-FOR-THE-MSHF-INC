import secrets

# Ambiguous glyphs removed (I/l/1, O/0) — this password gets read off a
# phone screen and retyped by hand, so lookalikes cost real support time.
ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
LENGTH = 12


def generate_temp_password(length=LENGTH):
    return ''.join(secrets.choice(ALPHABET) for _ in range(length))
