from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from courses.models import Course


@login_required
def course_chat_room(request, course_id):
    course = Course.objects.for_student(request.user).get(id=course_id)

    chat_messages = course.chat_messages.select_related('user').order_by('-created')[:50]
    chat_messages = reversed(chat_messages)

    return render(request, 'chat/room.html', {'course': course,
                                              'chat_messages': chat_messages})
