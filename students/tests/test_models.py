from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from courses.models import Subject, Course, Module, Quiz, Choice,Content,Question

User = get_user_model()


class QuizAttemptModelTest(TestCase):

    def setUp(self):
        """Configura los datos base que se usarán en cada test."""
        # 1. Creamos el Subject obligatorio
        self.subject = Subject.objects.create(
            title='Programación',
            slug='programacion'
        )

        # 2. Creamos los usuarios
        self.instructor = User.objects.create_user(
            username='profesor_prueba',
            password='password123'
        )
        self.student = User.objects.create_user(
            username='alumno_prueba',
            password='password123'
        )

        # 3. Creamos el curso inyectando subject y owner
        self.course = Course.objects.create(
            subject=self.subject,
            owner=self.instructor,
            title='Curso de Django Avanzado',
            slug='curso-django-avanzado'
        )
        self.module = Module.objects.create(
            course=self.course,
            title='Módulo 1: Arquitectura',
            description='Test de arquitectura'
        )

        # 4. Creamos el Quiz asignando su respectivo owner obligatorio (Corregido)
        self.quiz = Quiz.objects.create(
            title='Evaluación de Canales y WebSockets',
            owner=self.instructor
        )

    def test_quiz_attempt_passed_true(self):
        from students.models import QuizAttempt
        self.attempt = QuizAttempt.objects.create(
            student=self.student,
            quiz=self.quiz,
            score=7.50,
            correct_answers=3,
            total_questions=4,
            passed=True
        )
        self.assertTrue(self.attempt.passed)

    def test_quiz_attempt_score_validators(self):
        from students.models import QuizAttempt
        invalid_attempt = QuizAttempt(
            student=self.student,
            quiz=self.quiz,
            score=11.5,
            correct_answers=5,
            total_questions=4,
            passed=True
        )
        with self.assertRaises(ValidationError):
            invalid_attempt.full_clean()


class QuizSubmissionViewTest(TestCase):

    def setUp(self):
        # 1. Configuración básica de materias y usuarios
        self.subject = Subject.objects.create(title='Desarrollo Web', slug='desarrollo-web')
        self.instructor = User.objects.create_user(username='profesor_rest', password='securepass123')
        self.student = User.objects.create_user(username='carlos', password='securepass123')

        # 2. Creación del curso y módulo
        self.course = Course.objects.create(subject=self.subject, owner=self.instructor, title='Django REST',
                                            slug='django-rest')
        self.module = Module.objects.create(course=self.course, title='Módulo 1')
        self.quiz = Quiz.objects.create(title='Quiz Final', owner=self.instructor)

        # 3. VINCULACIÓN POLIMÓRFICA (Línea nueva indispensable para corregir el error)
        # Asociamos el Quiz al módulo a través del modelo Content genérico
        quiz_type = ContentType.objects.get_for_model(Quiz)
        Content.objects.create(
            module=self.module,
            content_type=quiz_type,
            object_id=self.quiz.id
        )

        # 4. Configuración de preguntas
        self.question = Question.objects.create(quiz=self.quiz, text='¿ASGI es asíncrono?')
        self.correct_choice = Choice.objects.create(question=self.question, text='Sí', is_correct=True)
        self.incorrect_choice = Choice.objects.create(question=self.question, text='No', is_correct=False)

        from django.urls import reverse
        self.submit_url = reverse('students:student_submit_quiz', kwargs={'quiz_id': self.quiz.id})

    def test_anonymous_user_cannot_submit(self):
        response = self.client.post(self.submit_url, data={})
        self.assertEqual(response.status_code, 302)

    def test_student_submits_perfect_quiz(self):
        from students.models import QuizAttempt
        self.client.login(username='carlos', password='securepass123')
        form_data = {
            f'question_{self.question.id}': self.correct_choice.id
        }
        response = self.client.post(self.submit_url, data=form_data)

        # Ahora que la vista encuentra el curso, redirigirá con éxito (Código 302)
        self.assertEqual(response.status_code, 302)

        attempt = QuizAttempt.objects.filter(student=self.student, quiz=self.quiz).first()
        self.assertIsNotNone(attempt)
        self.assertEqual(float(attempt.score), 10.0)


class CourseAccessRestrictionTest(TestCase):

    def setUp(self):
        # 1. Configuración de datos mínimos requeridos por tu estricta base de datos
        self.subject = Subject.objects.create(title='Seguridad', slug='seguridad')
        self.instructor = User.objects.create_user(username='profesor_sec', password='password123')
        self.student = User.objects.create_user(username='alumno_trampa', password='password123')

        self.course = Course.objects.create(subject=self.subject, owner=self.instructor, title='Hacking Django',
                                            slug='hacking-django')
        self.module = Module.objects.create(course=self.course, title='Módulo de Seguridad')

        # 2. Creamos un examen (Quiz) que estará en la posición inicial del módulo
        self.quiz = Quiz.objects.create(title='Quiz Inicial Obligatorio', owner=self.instructor)
        quiz_type = ContentType.objects.get_for_model(Quiz)
        self.quiz_content = Content.objects.create(
            module=self.module,
            content_type=quiz_type,
            object_id=self.quiz.id,
            order=1  # Posición 1
        )

        # 3. Creamos una lectura de texto avanzada que está DESPUÉS del examen
        from courses.models import Text
        self.text_item = Text.objects.create(title='Manual Avanzado', content='Contenido ultra secreto',
                                             owner=self.instructor)
        text_type = ContentType.objects.get_for_model(Text)
        self.advanced_content = Content.objects.create(
            module=self.module,
            content_type=text_type,
            object_id=self.text_item.id,
            order=2  # Posición 2 (Bloqueado hasta aprobar la posición 1)
        )

        # URL para intentar ver el curso con el parámetro del contenido avanzado
        from django.urls import reverse
        self.course_url = f"{reverse('students:student_course_detail', kwargs={'pk': self.course.id})}?content={self.advanced_content.id}"

    def test_student_blocked_if_quiz_not_passed(self):
        """Verifica que el sistema bloquee el acceso si el alumno no ha aprobado el examen previo."""
        # Logueamos al estudiante
        self.client.login(username='alumno_trampa', password='password123')

        # Intentamos ingresar directamente al contenido avanzado (orden 2) sin haber tocado el examen (orden 1)
        response = self.client.get(self.course_url)

        # La vista debe interceptar el peligro, lanzar un mensaje de error y redirigir (302) para salvaguardar el contenido
        self.assertEqual(response.status_code, 302)

        # Simulamos ahora que el alumno hace el examen pero lo REPRUEBA
        from students.models import QuizAttempt
        QuizAttempt.objects.create(
            student=self.student,
            quiz=self.quiz,
            score=4.0,  # Nota reprobatoria
            correct_answers=1,
            total_questions=3,
            passed=False
        )

        # Vuelve a intentar forzar la URL del contenido avanzado
        second_response = self.client.get(self.course_url)

        # Sigue bloqueado porque no ha obtenido el estatus de aprobado (passed=True)
        self.assertEqual(second_response.status_code, 302)
