import re

from django.core.exceptions import ValidationError

USERNAME_PATTERN = re.compile(r'^[A-Za-z0-9_-]{3,150}$')
USERNAME_ALLOWED_CHARS_PATTERN = re.compile(r'[^A-Za-z0-9_-]+')
USERNAME_MULTI_UNDERSCORE_PATTERN = re.compile(r'[_-]{2,}')


def validate_username_policy(username: str) -> str:
    # Keep the typed username as-is (only trim edges). Do not lower/sanitize.
    value = (username or '').strip()
    if not value:
        raise ValidationError('نام کاربری را وارد کن.')
    if len(value) < 3:
        raise ValidationError('نام کاربری باید حداقل ۳ کاراکتر باشد.')
    if len(value) > 150:
        raise ValidationError('نام کاربری نباید بیشتر از ۱۵۰ کاراکتر باشد.')
    if any(character.isspace() for character in value):
        raise ValidationError('نام کاربری نباید فاصله داشته باشد.')
    if not USERNAME_PATTERN.fullmatch(value):
        raise ValidationError('نام کاربری فقط باید شامل حروف انگلیسی، عدد، "-" یا "_" باشد.')
    return value


def sanitize_legacy_username(username: str, fallback: str) -> str:
    raw = (username or '').strip().lower().replace(' ', '_')
    raw = USERNAME_ALLOWED_CHARS_PATTERN.sub('_', raw)
    raw = USERNAME_MULTI_UNDERSCORE_PATTERN.sub('_', raw)
    raw = raw.strip('_-')
    if len(raw) < 3:
        raw = fallback
    return raw[:150]
