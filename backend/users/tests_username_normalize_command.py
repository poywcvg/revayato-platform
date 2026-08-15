from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

User = get_user_model()


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class NormalizeUsernamesCommandTests(TestCase):
    def test_command_normalizes_invalid_usernames_and_sends_email(self):
        user = User.objects.create_user(
            email='legacy@example.com',
            username='کاربر قدیمی',
            password='SafePass123!',
        )

        out = StringIO()
        call_command('normalize_usernames', stdout=out)

        user.refresh_from_db()
        self.assertTrue(user.username.startswith('user'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('نام کاربری جدید', mail.outbox[0].body)

    def test_dry_run_does_not_persist_or_email(self):
        user = User.objects.create_user(
            email='legacy2@example.com',
            username='نام تست',
            password='SafePass123!',
        )
        old = user.username

        call_command('normalize_usernames', '--dry-run')

        user.refresh_from_db()
        self.assertEqual(user.username, old)
        self.assertEqual(len(mail.outbox), 0)
