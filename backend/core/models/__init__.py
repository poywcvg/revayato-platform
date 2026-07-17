import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


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


class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class SlugModel(models.Model):
    slug = models.SlugField(_('Slug'), max_length=255, unique=True, db_index=True, allow_unicode=True)

    class Meta:
        abstract = True


class TitleSlugModel(TimeStampedModel, SlugModel):
    title = models.CharField(_('Title'), max_length=255, db_index=True)
    original_title = models.CharField(_('Original Title'), max_length=255, blank=True)

    class Meta:
        abstract = True
        ordering = ['title']

    def __str__(self):
        return self.title


class PublishableModel(models.Model):
    is_published = models.BooleanField(_('Published'), default=False, db_index=True)
    published_at = models.DateTimeField(_('Published At'), null=True, blank=True, db_index=True)

    class Meta:
        abstract = True


class SEOMixin(models.Model):
    meta_title = models.CharField(_('Meta Title'), max_length=255, blank=True)
    meta_description = models.TextField(_('Meta Description'), blank=True)
    meta_keywords = models.TextField(_('Meta Keywords'), blank=True)
    og_title = models.CharField(_('OG Title'), max_length=255, blank=True)
    og_description = models.TextField(_('OG Description'), blank=True)
    og_image = models.ImageField(_('OG Image'), upload_to='seo/', blank=True)

    class Meta:
        abstract = True


class SEOModelMixin(SEOMixin):
    class Meta:
        abstract = True


class MediaMixin(models.Model):
    poster = models.ImageField(_('Poster'), upload_to='posters/', blank=True, null=True)
    backdrop = models.ImageField(_('Backdrop'), upload_to='backdrops/', blank=True, null=True)

    class Meta:
        abstract = True


class RatingMixin(models.Model):
    imdb_rating = models.DecimalField(_('IMDb Rating'), max_digits=3, decimal_places=1, null=True, blank=True, db_index=True)
    site_rating = models.DecimalField(_('Site Rating'), max_digits=3, decimal_places=1, null=True, blank=True, db_index=True)
    vote_count = models.PositiveIntegerField(_('Vote Count'), default=0)

    class Meta:
        abstract = True


class ViewLikeMixin(models.Model):
    view_count = models.PositiveBigIntegerField(_('View Count'), default=0, db_index=True)
    like_count = models.PositiveIntegerField(_('Like Count'), default=0, db_index=True)

    class Meta:
        abstract = True

    def increment_views(self):
        self.__class__.objects.filter(pk=self.pk).update(view_count=models.F('view_count') + 1)
        self.refresh_from_db(fields=['view_count'])

    def increment_likes(self):
        self.__class__.objects.filter(pk=self.pk).update(like_count=models.F('like_count') + 1)
        self.refresh_from_db(fields=['like_count'])

    def decrement_likes(self):
        self.__class__.objects.filter(pk=self.pk).update(like_count=models.F('like_count') - 1)
        self.refresh_from_db(fields=['like_count'])