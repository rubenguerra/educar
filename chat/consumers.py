import json
import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from courses.models import Course
from .models import ChatMessage


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        # acepta la conexión
        self.course_id = self.scope['url_route']['kwargs']['course_id']
        self.room_group_name = f'chat_{self.course_id}'
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # dejar el grupo
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # recibe el mensaje de WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        # control de seguridad para usuario solo autenticado.
        username = self.user.username if self.user.is_authenticated else 'Anonymous'
        if self.user.is_authenticated:
            await self.save_message(self.course_id, self.user, message)
        # envía el mensaje al grupo en la sala
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'user': username,
            }
        )

    async def chat_message(self, event):

        await self.send(text_data=json.dumps({
            'message': event['message'],
            'user': event.get('user', 'Anonymous'),
            'datetime': datetime.datetime.now().isoformat()
        }))

    # ---Método auxiliar de alto rendimiento ---
    @database_sync_to_async
    def save_message(self, course_id, user, message):
        course = Course.objects.get(id=course_id)
        return ChatMessage.objects.create(course=course, user=user,
                                          message=message)
