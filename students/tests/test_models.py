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

    def test_student_exceeds_max_attempts_is_blocked(self):
        """Verifica que el sistema rechace y bloquee al alumno al intentar un 4to envío en menos de 24 horas."""
        self.client.login(username='carlos', password='securepass123')
        form_data = {f'question_{self.question.id}': self.incorrect_choice.id}

        # Simula 3 intentos fallidos consecutivos en el mismo instante
        from students.models import QuizAttempt
        for _ in range(3):
            QuizAttempt.objects.create(
                student=self.student,
                quiz=self.quiz,
                score=2.0,
                correct_answers=0,
                total_questions=1,
                passed=False
            )

        # Se ejecuta la cuarta petición POST real a la vista
        response = self.client.post(self.submit_url, data=form_data)

        # Debe saltar la redirección preventiva de seguridad (302)
        self.assertEqual(response.status_code, 302)

        # Confirmamos que NO se creó un cuarto intento en la base de datos
        total_intentos = QuizAttempt.objects.filter(student=self.student, quiz=self.quiz).count()
        self.assertEqual(total_intentos, 3)


class CourseAccessRestrictionTest(TestCase):

    def setUp(self):
        # 1. Configuración de datos mínimos requeridos
        self.subject = Subject.objects.create(title='Seguridad', slug='seguridad')
        self.instructor = User.objects.create_user(username='profesor_sec', password='password123')
        self.student = User.objects.create_user(username='alumno_trampa', password='password123')

        # 2. Creamos el curso e INSCRIBIMOS al alumno para evitar el error 404 de seguridad
        self.course = Course.objects.create(
            subject=self.subject,
            owner=self.instructor,
            title='Hacking Django',
            slug='hacking-django'
        )
        self.course.students.add(self.student)  # <--- ¡Línea clave de inscripción!

        self.module = Module.objects.create(course=self.course, title='Módulo de Seguridad')

        # 3. Creamos un examen (Quiz) en la posición inicial (order=1)
        self.quiz = Quiz.objects.create(title='Quiz Inicial Obligatorio', owner=self.instructor)
        quiz_type = ContentType.objects.get_for_model(Quiz)
        self.quiz_content = Content.objects.create(
            module=self.module,
            content_type=quiz_type,
            object_id=self.quiz.id,
            order=1
        )

        # 4. Creamos una lectura avanzada en la posición siguiente (order=2)
        from courses.models import Text
        self.text_item = Text.objects.create(title='Manual Avanzado', content='Contenido ultra secreto',
                                             owner=self.instructor)
        text_type = ContentType.objects.get_for_model(Text)
        self.advanced_content = Content.objects.create(
            module=self.module,
            content_type=text_type,
            object_id=self.text_item.id,
            order=2
        )

        # 5. Generamos la URL usando 'pk' de forma idéntica a tu archivo urls.py
        from django.urls import reverse
        self.course_url = f"{reverse('students:student_course_detail', kwargs={'pk': self.course.id})}?content={self.advanced_content.id}"

    def test_student_blocked_if_quiz_not_passed(self):
        """Verifica que el sistema bloquee el acceso si el alumno no ha aprobado el examen previo."""
        # Iniciamos sesión con el alumno inscrito
        self.client.login(username='alumno_trampa', password='password123')

        # Intenta entrar al contenido avanzado (order=2) sin hacer el examen (order=1)
        response = self.client.get(self.course_url)

        # La vista ahora sí lo reconoce, ejecuta can_access_content, detecta el bloqueo y lo redirige (302)
        self.assertEqual(response.status_code, 302)

        # Simulamos que toma el examen pero saca un 4.0 (reprobado)
        from students.models import QuizAttempt
        QuizAttempt.objects.create(
            student=self.student,
            quiz=self.quiz,
            score=4.0,
            correct_answers=1,
            total_questions=3,
            passed=False
        )

        # Intenta forzar la entrada otra vez
        second_response = self.client.get(self.course_url)

        # Debe mantenerse redirigido/bloqueado (302) porque no ha aprobado
        self.assertEqual(second_response.status_code, 302)
