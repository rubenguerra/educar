from django.db import models
from django.contrib.auth.models import User
from courses.models import Course


class ChatMessage(models.Model):
    course = models.ForeignKey(Course,
                               related_name='chat_messages',
                               on_delete=models.CASCADE)
    user = models.ForeignKey(User,
                             related_name='chat_messages',
                             on_delete=models.CASCADE)
    message = models.TextField()
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created']

    def __str__(self):
        return f'{self.user.username}: {self.message[:30]}'
