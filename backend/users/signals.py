from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

from users.models import User, UserProfile, UserTasteProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)
        UserTasteProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()
    if hasattr(instance, 'taste_profile'):
        instance.taste_profile.save()