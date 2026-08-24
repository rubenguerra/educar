from django.urls import path, include
from rest_framework import routers
from . import views

app_name = 'courses'

router = routers.SimpleRouter()
router.register('courses', views.CourseViewSet, basename='course')

urlpatterns = [
    path('subjects/', views.SubjectListView.as_view(), name='subject_list'),
    path('subjects/<int:pk>/', views.SubjectDetailView.as_view(), name='subject_detail'),
    path('', include(router.urls)),
]