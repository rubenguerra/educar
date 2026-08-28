import json
from django.contrib.auth import get_user_model
from channels.testing import ChannelsLiveServerTestCase, WebsocketCommunicator
from unittest.mock import AsyncMock, patch

from courses.models import Subject, Course, Module
from students.consumers import AIChatConsumer
from students.models import ChatMessage

User = get_user_model()


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
