import json
from django.contrib.auth import get_user_model
from channels.testing import ChannelsLiveServerTestCase, WebsocketCommunicator
from channels.db import database_sync_to_async

from courses.models import Subject, Course
from chat.consumers import ChatConsumer  # Importamos el consumer de humanos
from chat.models import ChatMessage  # Reemplaza  el modelo real de mensajes de chat humano

User = get_user_model()


class UserChatConsumerTest(ChannelsLiveServerTestCase):

    def setUp(self):
        """Configuración de la estructura de base de datos para el chat humano."""
        self.subject = Subject.objects.create(title='Web', slug='web')
        self.instructor = User.objects.create_user(username='profesor_chat', password='password123')

        # Creamos dos estudiantes de prueba
        self.student_a = User.objects.create_user(username='carlos_a', password='password123')
        self.student_b = User.objects.create_user(username='maria_b', password='password123')

        self.course = Course.objects.create(
            subject=self.subject,
            owner=self.instructor,
            title='Curso Canales',
            slug='curso-canales'
        )
        self.course.students.add(self.student_a, self.student_b)

        # Guardamos llaves primarias
        self.course_id = self.course.id
        self.student_a_id = self.student_a.id

        # ----------------------------------------------------
        # CONFIGURACIÓN DE LOS DOS COMUNICADORES EN PARALELO
        # ----------------------------------------------------
        # Comunicador para el Estudiante A
        self.communicator_a = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/room/{self.course_id}/")
        self.communicator_a.scope['user'] = self.student_a
        self.communicator_a.scope['url_route'] = {'kwargs': {'course_id': str(self.course_id)}}

        # Comunicador para el Estudiante B
        self.communicator_b = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/room/{self.course_id}/")
        self.communicator_b.scope['user'] = self.student_b
        self.communicator_b.scope['url_route'] = {'kwargs': {'course_id': str(self.course_id)}}

    async def test_broadcast_message_between_users(self):
        """Verifica que un mensaje enviado por un usuario sea recibido por los demás en la sala."""

        # 1. Conectamos a ambos estudiantes al WebSocket
        connected_a, _ = await self.communicator_a.connect()
        connected_b, _ = await self.communicator_b.connect()
        self.assertTrue(connected_a)
        self.assertTrue(connected_b)

        # 2. El Estudiante A envía un mensaje al canal del grupo
        await self.communicator_a.send_to(text_data=json.dumps({
            'message': '¡Hola a todos en la clase!'
        }))

        # 3. El Estudiante B debe recibir el mensaje transmitido (Broadcast) por el servidor
        response_b = await self.communicator_b.receive_from()
        data_b = json.loads(response_b)

        # Verificamos que el contenido y los metadatos correspondan al remitente original
        self.assertEqual(data_b['message'], '¡Hola a todos en la clase!')
        self.assertEqual(data_b['user'], 'carlos_a')

        # 4. Validar que el mensaje se guardó físicamente en la Base de Datos
        from channels.db import database_sync_to_async
        count = await database_sync_to_async(
            lambda: ChatMessage.objects.filter(user_id=self.student_a_id, course_id=self.course_id).count()
        )()
        self.assertEqual(count, 1)

        # 5. Desconexión limpia de ambos clientes
        await self.communicator_a.disconnect()
        await self.communicator_b.disconnect()
