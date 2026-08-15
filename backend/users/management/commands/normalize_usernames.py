from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from users.username_policy import sanitize_legacy_username, validate_username_policy

User = get_user_model()


class Command(BaseCommand):
    help = 'Normalize legacy usernames to English-only format and notify users by email.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without saving or sending emails.',
        )
        parser.add_argument(
            '--skip-email',
            action='store_true',
            help='Apply username changes without sending notification emails.',
        )

    def handle(self, *args, **options):
        dry_run = bool(options['dry_run'])
        skip_email = bool(options['skip_email'])
        changed = 0
        emailed = 0
        failed_emails = 0

        users = User.all_objects.only('id', 'email', 'username').order_by('id')
        for user in users.iterator():
            old_username = user.username or ''
            if self._is_valid(old_username):
                continue
            new_username = self._build_unique_username(user)
            changed += 1
            self.stdout.write(
                f'user#{user.id}: "{old_username}" -> "{new_username}"',
            )
            if dry_run:
                continue
            User.all_objects.filter(pk=user.pk).update(username=new_username)
            if skip_email:
                continue
            if self._notify_user(user.email, old_username, new_username):
                emailed += 1
            else:
                failed_emails += 1

        mode = 'DRY RUN' if dry_run else 'APPLIED'
        self.stdout.write(self.style.SUCCESS(
            f'[{mode}] changed={changed} emailed={emailed} email_failed={failed_emails}',
        ))

    def _is_valid(self, username: str) -> bool:
        try:
            validate_username_policy(username)
            return True
        except Exception:  # noqa: BLE001
            return False

    def _build_unique_username(self, user) -> str:
        base = sanitize_legacy_username(
            user.username,
            fallback=f'user{user.id}',
        )
        candidate = base
        suffix = 1
        while User.all_objects.filter(username__iexact=candidate).exclude(pk=user.pk).exists():
            suffix += 1
            postfix = f'_{suffix}'
            candidate = f'{base[:150 - len(postfix)]}{postfix}'
        return candidate

    def _notify_user(self, email: str, old_username: str, new_username: str) -> bool:
        if not email:
            return False
        try:
            send_mail(
                subject='تغییر نام کاربری حساب شما در روایتو',
                message=(
                    'برای یکپارچه‌سازی سیستم، نام کاربری شما به فرمت انگلیسی تغییر داده شد.\n\n'
                    f'نام کاربری قبلی: {old_username}\n'
                    f'نام کاربری جدید: {new_username}\n\n'
                    'اگر این تغییر را خودتان انجام نداده‌اید یا سوالی دارید، با پشتیبانی تماس بگیرید.'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            return True
        except Exception:  # noqa: BLE001
            return False
