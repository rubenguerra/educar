from django.urls import path
from . import views

app_name = 'students'

urlpatterns = [
    path('registro/', views.StudentRegistrationView.as_view(), name='student_registration'),
    path('inscribir_curso/', views.StudentEnrollCourseView.as_view(), name='student_enroll_course'),
    path('cursos/', views.StudentCourseListView.as_view(), name='student_course_list'),
    path('curso/<int:pk>/', views.StudentCourseDetailView.as_view(), name='student_course_detail'),
    path('curso/<int:pk>/<int:module_id>/', views.StudentCourseDetailView.as_view(),
         name='student_course_detail_module'),
    path('quiz/<int:quiz_id>/submit/', views.student_submit_quiz, name='student_submit_quiz'),
    path('attempt/<int:attempt_id>/', views.quiz_attempt_detail, name='quiz_attempt_detail'),
]