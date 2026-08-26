from django.urls import path
from . import views

app_name = 'courses'

urlpatterns = [
    path('mios/', views.ManageCourseListView.as_view(), name='manage_course_list'),
    path('crear/', views.CourseCreateView.as_view(), name='course_create'),
    path('<int:pk>/editar/', views.CourseUpdateView.as_view(), name='course_edit'),
    path('<int:pk>/eliminar/', views.CourseDeleteView.as_view(), name='course_delete'),
    path('<int:pk>/modulo/', views.CourseModuleUpdateView.as_view(), name='course_module_update'),
    path('module/<int:module_id>/content/<str:model_name>/create/',
         views.ContentCreateUpdateView.as_view(), name='module_content_create'),
    path('module/<int:module_id>/content/<str:model_name>/<int:id>/',
         views.ContentCreateUpdateView.as_view(), name='module_content_update'),
    path('content/<int:id>/delete/', views.ContentDeleteView.as_view(), name='module_content_delete'),
    path('module/<int:module_id>/', views.ModuleContentListView.as_view(), name='module_content_list'),
    path('module/<int:order>/', views.ModuleOrderView.as_view(), name='module_order'),
    path('content/<int:order>/', views.ContentOrderView.as_view(), name='content_order'),
    path('tema/<slug:subject>/', views.CourseListView.as_view(), name='course_list_subject'),
    path('<slug:slug>/', views.CourseDetailView.as_view(), name='course_detail'),
    path('<int:course_id>/analytics/', views.generate_course_ai_analytics, name='course_ai_analytics'),
]