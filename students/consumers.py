import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from openai import AsyncOpenAI  # Importación del cliente no-bloqueante
from .models import ChatMessage
from courses.models import Course, Content


class AIChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close()
            return

        self.course_id = self.scope['url_route']['kwargs']['course_id']
        self.room_group_name = f'chat_{self.user.id}_{self.course_id}'

        # Inicializamos el cliente asíncrono de OpenAI
        self.ai_client = AsyncOpenAI()

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Se recuperan los últimos 10 mensajes de la base de datos
        history = await self.get_conversation_history(user=self.user, course_id=self.course_id, limit=10)
        if history:
            await self.send(text_data=json.dumps({'status': 'history',
                                                  'messages': history}))

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        """Recibe el mensaje del estudiante y genera una respuesta ultra personalizada con contexto."""
        text_data_json = json.loads(text_data)
        user_message = text_data_json.get('message', '').strip()

        if not user_message:
            return

        # 1. Guardar el mensaje del alumno en la BD
        await self.save_message(user=self.user, course_id=self.course_id, role='user', text=user_message)

        # 2. Informar al frontend confirmación de recepción
        await self.send(json.dumps({'status': 'received',
                                    'message': user_message,
                                    'role': 'user'}))

        # 3. EXTRAER EL CONTEXTO EN TIEMPO REAL (Línea nueva y clave)
        student_context = await self.get_student_academic_context(user=self.user, course_id=self.course_id)

         # EXTRAER MATERIAL DE ESTUDIO
        course_material = await self.get_course_material_contex(course_id=self.course_id)

        # 4. Recuperar el historial de chat (Memoria conversacional)
        conversation_history = await self.get_conversation_history(user=self.user, course_id=self.course_id)

        try:
            # 5. Configurar el System Prompt inyectando las variables académicas
            system_prompt = (
                f"Eres un tutor de Inteligencia Artificial experto y ultra personalizado para la plataforma 'EDUCA'.\n"
                f"Estás asistiendo de forma privada al estudiante '{self.user.username}'.\n\n"
                f"Tu principal fuente de verdad es el siguiente material de estudio oficial del curso. "
                f"Si el alumno te hace preguntas teóricas, debes responder basándote estrictamente en este contenido, "
                f"explicándolo de forma pedagógica, clara y profunda:\n\n"
                f"{course_material}\n\n"
                f"Información de progreso actual del usuario para personalizar tu tono:\n"
                f"{student_context}\n\n"
                f"REGLAS OBLIGATORIAS DE COMPORTAMIENTO:\n"
                f"1. Si el tema consultado NO está en el material de estudio, puedes usar tu conocimiento general "
                f"para complementar, pero prioriza siempre la terminología y estructura del curso oficial.\n"
                f"2. Nunca inventes lecturas o contenidos que no estén listados en el bloque de arriba.\n"
                f"3. Mantén la regla socrática: guía al alumno con pistas e hilos lógicos en lugar de darle respuestas "
                f"directas de sus evaluaciones."
            )

            # Estructurar la carga de mensajes para OpenAI
            messages_payload = [{"role": "system", "content": system_prompt}]

            for msg in conversation_history:
                role_mapping = "assistant" if msg['sender_role'] == 'ai' else "user"
                messages_payload.append({"role": role_mapping, "content": msg['message']})

            # Añadir el mensaje de este momento
            messages_payload.append({"role": "user", "content": user_message})

            # 6. Llamada asíncrona a OpenAI (gpt-4o-mini es idóneo por su velocidad)
            response = await self.ai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages_payload,
                max_tokens=700,
                temperature=0.5
            )

            ai_response = response.choices.message.content.strip()

        except Exception as e:
            ai_response = f"Lo siento, estoy experimentando dificultades técnicas para procesar tu consulta en este momento. (Error: {str(e)})"

        # 7. Guardar la respuesta generada por la IA
        await self.save_message(user=self.user, course_id=self.course_id, role='ai', text=ai_response)
        # 8. Despachar la respuesta de la IA al WebSocket
        await self.send(json.dumps({'status': 'success',
                                    'message': ai_response,
                                    'role': 'ai'}))

    @database_sync_to_async
    def get_conversation_history(self, user, course_id, limit=10):
        """Recupera los últimos N mensajes para que el Bot mantenga el hilo de la conversación."""
        messages_queryset = ChatMessage.objects.filter(
            user=user,
            course_id=course_id
        ).order_by('-timestamp')[:limit]

        # Invertimos el orden para pasárselo de forma cronológica (antiguo -> nuevo) a la IA
        return list(reversed([
            {'sender_role': msg.sender_role, 'message': msg.message}
            for msg in messages_queryset
        ]))

    @database_sync_to_async
    def save_message(self, user, course_id, role, text):
        """Método utilitario para interactuar con el ORM de Django de forma asíncrona."""
        course = Course.objects.filter(id=course_id).first()
        return ChatMessage.objects.create(
            user=user,
            course=course,
            sender_role=role,
            message=text
        )

    @database_sync_to_async
    def get_student_academic_context(self, user, course_id):
        """
        Recopila el progreso actual y el historial de exámenes del alumno
        en este curso para generar un informe de contexto textual para la IA.
        """
        from students.models import StudentProgress, QuizAttempt
        from courses.models import Course

        course = Course.objects.filter(id=course_id).first()
        if not course:
            return "Información del curso no disponible."

        # 1. Obtener progreso de contenidos completados
        progress = StudentProgress.objects.filter(student=user, course=course).first()
        total_contents = sum(module.contents.count() for module in course.modules.all())
        completed_count = progress.completed_contents.count() if progress else 0

        # 2. Obtener el historial detallado de intentos de examen en este curso
        attempts = QuizAttempt.objects.filter(
            student=user,
            quiz__module__course=course
        ).select_related('quiz').order_by('quiz_id', '-taken_at')

        # Estructuramos el reporte en texto plano
        context_text = f"--- CONTEXTO ACADÉMICO DEL ESTUDIANTE ---\n"
        context_text += f"Curso Actual: {course.title}\n"
        context_text += f"Progreso General del Curso: {completed_count} de {total_contents} contenidos completados.\n\n"

        context_text += "Historial de Evaluaciones y Quizzes:\n"

        if not attempts.exists():
            context_text += "- El estudiante aún no ha realizado ningún examen en este curso.\n"
        else:
            # Agrupamos o listamos los intentos de forma clara para el prompt
            current_quiz_id = None
            for att in attempts:
                if att.quiz_id != current_quiz_id:
                    context_text += f"\n* Examen: '{att.quiz.title}':\n"
                    current_quiz_id = att.quiz_id

                estado = "APROBADO" if att.passed else "REPROBADO"
                context_text += (
                    f"  - Intento el {att.taken_at.strftime('%d/%m/%Y')}: "
                    f"Nota {att.score}/10.0 ({att.correct_answers}/{att.total_questions} aciertos). "
                    f"Estado: {estado}.\n"
                )

        context_text += "----------------------------------------"
        return context_text

    @database_sync_to_async
    def get_course_material_contex(self, course_id):
        """
        Toma el temario y el contenido textual de los módulos del curso para
        que la IA actúe como un experto del material oficial.
        """
        course = Course.objects.filter(id=course_id).prefetch_related('modules__contents').first()
        if not course:
            return 'Material de estudio no disponible.'

        material_text = "--- MATERIAL DE ESTUDIO OFICIAL DEL CURSO ---\n"

        for module in course.modules.all():
            material_text += f'\nMódulo: {module.title}\n'
            material_text += f'Descripción del Módulo: {module.description}\n'

            for content in module.contents.all():
                content_model = content.content_type.model
                item = content.item

                if content_model == 'text':
                    material_text += f' - Lectura [{item.title}]: {item.content}\n'
                elif content_model == 'video':
                    material_text += f" - Video Disponible: '{item.title}' (URL o recurso multimedia asociado).\n"
                elif content_model == 'quiz':
                    material_text += f" - Evaluación del Módulo: '{item.title}' Contiene preguntas de autoevaluación teórica.\n"

            material_text += "-----------------------------------------------------"
            return material_text
