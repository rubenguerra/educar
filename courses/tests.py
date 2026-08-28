from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from courses.models import Subject, Course

User = get_user_model()


class TeacherCourseManagementTest(TestCase):

    def setUp(self):
        """Configura dos profesores con permisos totales de Instructores y sus cursos."""
        self.subject = Subject.objects.create(title='Matemáticas', slug='matematicas')

        # 1. Obtenemos los permisos nativos de Django para el modelo Course
        content_type = ContentType.objects.get_for_model(Course)
        # Buscamos los 4 permisos principales de CRUD
        permissions = Permission.objects.filter(
            content_type=content_type,
            codename__in=['add_course', 'change_course', 'delete_course', 'view_course']
        )

        # 2. Creamos al Profesor A y le otorgamos rol de staff y sus permisos
        self.teacher_a = User.objects.create_user(
            username='profesor_a',
            password='password123',
            is_staff=True  # Mantenemos staff por si tus mixins heredan de StaffuserRequiredMixin
        )
        # Asignamos los permisos en lote
        self.teacher_a.user_permissions.set(permissions)

        self.course_a = Course.objects.create(
            subject=self.subject,
            owner=self.teacher_a,
            title='Álgebra Lineal',
            slug='algebra-lineal'
        )

        # 3. Creamos al Profesor B con la misma configuración de Instructor
        self.teacher_b = User.objects.create_user(
            username='profesor_b',
            password='password123',
            is_staff=True
        )
        self.teacher_b.user_permissions.set(permissions)

        self.course_b = Course.objects.create(
            subject=self.subject,
            owner=self.teacher_b,
            title='Cálculo Diff',
            slug='calculo-diff'
        )

    def test_teacher_can_access_their_own_course_list(self):
        """Verifica que el profesor logueado vea únicamente sus cursos en el panel."""
        self.client.login(username='profesor_a', password='password123')

        url = reverse('courses:manage_course_list')
        response = self.client.get(url)

        # Al contar con permisos explícitos de CRUD y Staff, el Mixin autorizará el acceso (200)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Álgebra Lineal')
        self.assertNotContains(response, 'Cálculo Diff')

    def test_teacher_cannot_edit_other_teacher_course(self):
        """Regla de seguridad: Un profesor no puede editar el curso de otro."""
        self.client.login(username='profesor_a', password='password123')

        # AGREGA EL NAMESPACE 'courses:' ANTES DEL NOMBRE DE LA URL:
        url = reverse('courses:course_edit', kwargs={'pk': self.course_b.id})
        response = self.client.get(url)

        # Validamos que tu QuerySet seguro responda con un 404 de privacidad
        self.assertEqual(response.status_code, 404)


