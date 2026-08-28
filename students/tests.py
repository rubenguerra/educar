import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType

from channels.testing import ChannelsLiveServerTestCase, WebsocketCommunicator
from unittest.mock import AsyncMock, patch

from courses.models import Subject, Course, Module, Quiz, Choice,Content,Question
from students.consumers import AIChatConsumer
from students.models import ChatMessage


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

class AIChatConsumerTest(ChannelsLiveServerTestCase):

    def setUp(self):
        """Configuración estándar y segura de datos de prueba."""
        # 1. Creamos la estructura base mínima requerida en la Base de Datos
        self.subject = Subject.objects.create(title='IA', slug='ia')
        self.instructor = User.objects.create_user(username='profesor_ia', password='password123')
        self.student = User.objects.create_user(username='alumno_ia', password='password123')

        self.course = Course.objects.create(
            subject=self.subject,
            owner=self.instructor,
            title='Curso IA',
            slug='curso-ia'
        )
        self.course.students.add(self.student)
        self.module = Module.objects.create(course=self.course, title='Módulo 1')

        # 2. Guardamos las llaves primarias numéricas
        self.course_id = self.course.id
        self.student_id = self.student.id

        # 3. Inicializamos el comunicador apuntando a nuestro Consumer
        self.communicator = WebsocketCommunicator(
            AIChatConsumer.as_asgi(),
            f"/ws/chat/{self.course_id}/"
        )
        self.communicator.scope['user'] = self.student
        self.communicator.scope['url_route'] = {
            'kwargs': {'course_id': str(self.course_id)}
        }

    # Parchamos las dos funciones del ORM y la CLASE local AsyncOpenAI que usa tu consumer
    @patch('students.consumers.AIChatConsumer.get_conversation_history')
    @patch('students.consumers.AIChatConsumer.get_student_academic_context')
    @patch('students.consumers.AsyncOpenAI')  # <--- PARCHE DE CLIENTE LOCAL (Magia pura)
    async def test_chat_communication_workflow(self, mock_openai_class, mock_academic_context, mock_history):
        """Prueba el ciclo completo de WebSockets de forma aislada y libre de errores de hilos."""

        # 1. Simulamos el historial y el contexto académico para evitar consultas síncronas/pesadas
        mock_history.return_value = [
            {'sender_role': 'user', 'message': 'Hola, soy un mensaje de historial simulado.'}
        ]
        mock_academic_context.return_value = "Contexto académico simulado para pruebas."

        # 2. Creamos la estructura de datos que emula de forma idéntica a OpenAI
        class MockMessage:
            content = "Esta es una respuesta simulada del Tutor de IA."

        class MockChoice:
            message = MockMessage()

        class MockResponse:
            # Soportamos la sintaxis de lista: response.choices[0].message.content
            choices = [MockChoice()]

            # Por si acaso tu consumer usa response.choices.message.content directamente:
            @property
            def message(self):
                return MockMessage()

        # Función asíncrona nativa pura para resolver el await
        async def mock_create_completion(*args, **kwargs):
            return MockResponse()

        # Vinculamos la corrutina al cliente mockeado de tu consumer
        mock_client_instance = mock_openai_class.return_value
        mock_client_instance.chat.completions.create = mock_create_completion

        # 3. Conectar al WebSocket de pruebas
        connected, _ = await self.communicator.connect()
        self.assertTrue(connected)

        # 4. Consumir el paquete inicial del historial
        history_response = await self.communicator.receive_from()
        history_data = json.loads(history_response)
        self.assertEqual(history_data['status'], 'history')

        # 5. Enviar una duda desde el frontend simulado hacia el WebSocket
        await self.communicator.send_to(text_data=json.dumps({
            'message': '¿Qué es un WebSocket?'
        }))

        # 6. Esperar y validar la confirmación inmediata del servidor
        received_response = await self.communicator.receive_from()
        received_data = json.loads(received_response)
        self.assertEqual(received_data['status'], 'received')

        # 7. Recibir y validar la respuesta definitiva generada por nuestra corrutina nativa
        success_response = await self.communicator.receive_from()
        success_data = json.loads(success_response)
        self.assertEqual(success_data['status'], 'success')
        self.assertEqual(success_data['message'], "Esta es una respuesta simulada del Tutor de IA.")

        # 8. Validar el impacto de persistencia en la base de datos usando IDs
        from channels.db import database_sync_to_async
        count = await database_sync_to_async(
            lambda: ChatMessage.objects.filter(user_id=self.student_id, course_id=self.course_id).count()
        )()
        self.assertEqual(count, 2)

        # 9. Desconectar de forma limpia
        await self.communicator.disconnect()
