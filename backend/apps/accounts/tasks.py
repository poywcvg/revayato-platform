"""Housekeeping for the long-lived session store.

A session is meant to survive until the user logs out, which means refresh
tokens rotate for up to ``JWT_REFRESH_TOKEN_DAYS`` (400) days. Every rotation
writes one ``OutstandingToken`` row plus one ``BlacklistedToken`` row and
SimpleJWT never removes either, so an active browser adds a row per access-token
expiry — roughly a dozen a day, forever. Left alone the table reaches millions of
rows, and the queries that keep a session alive slow down with it: exactly the
"it logged me out" symptom the long window exists to prevent.

Rows whose ``expires_at`` has passed cannot authorise anything, so deleting them
is safe: the blacklist only has to outlive the token it refuses.
"""

from celery import shared_task
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

# Deleting in slices keeps each transaction (and the cascade to BlacklistedToken)
# short enough not to hold locks on a table the refresh endpoint reads.
FLUSH_BATCH_SIZE = 5_000
FLUSH_MAX_BATCHES = 200


@shared_task(name='apps.accounts.tasks.flush_expired_tokens_task')
def flush_expired_tokens_task():
    """Delete refresh tokens that have expired on their own.

    Equivalent to SimpleJWT's ``flushexpiredtokens`` management command, but
    batched and callable from beat. ``BlacklistedToken`` rows disappear with
    their ``OutstandingToken`` through the FK cascade.
    """
    now = timezone.now()
    deleted = 0
    for _batch in range(FLUSH_MAX_BATCHES):
        expired_ids = list(
            OutstandingToken.objects.filter(expires_at__lte=now)
            .values_list('id', flat=True)[:FLUSH_BATCH_SIZE]
        )
        if not expired_ids:
            break
        removed, _details = OutstandingToken.objects.filter(id__in=expired_ids).delete()
        if not removed:
            break
        deleted += len(expired_ids)
    return {
        'deleted': deleted,
        'outstanding_remaining': OutstandingToken.objects.count(),
        'blacklisted_remaining': BlacklistedToken.objects.count(),
    }
