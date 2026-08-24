from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import Course, Subject


def clear_courses_cache(course_instance=None):
    # Función auxiliar para borrar llaves de caché relacionada a los cursos.
    cache.delete('all_subjects')
    cache.delete('all_courses')
    if course_instance and course_instance.subject:
        cache.delete(f'subject_{course_instance.subject.id}_courses')


@receiver(post_save, sender=Course)
@receiver(post_delete, sender=Course)
def invalidate_course_cache(sender, instance, **kwargs):
    clear_courses_cache(course_instance=instance)


@receiver(post_save, sender=Subject)
@receiver(post_delete, sender=Subject)
def invalidate_subject_cache(sender, instance, **kwargs):
    clear_courses_cache()