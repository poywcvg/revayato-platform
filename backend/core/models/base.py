from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(_('Is Deleted'), default=False, db_index=True)
    deleted_at = models.DateTimeField(_('Deleted At'), null=True, blank=True)

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.deleted_at = models.functions.Now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

    def hard_delete(self):
        super().delete()

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at'])


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True

import uuid