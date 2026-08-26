from courses.models import Content
from students.models import QuizAttempt


def can_access_content(student, content):
    """
    Verifica si el estudiante ha aprobado todos los exámenes
    previos dentro del mismo módulo antes de acceder a este contenido.
    """
    # 1. Obtener todos los contenidos del mismo módulo ordenados
    module_contents = Content.objects.filter(
        module=content.module
    ).order_by('order')  # Asumiendo que usas un campo 'order' o 'id'

    # 2. Revisar los contenidos anteriores al actual
    for previous_content in module_contents:
        if previous_content.order >= content.order:
            break  # Ya llegamos al contenido actual, los anteriores están limpios

        # 3. Si el contenido anterior es un Quiz (examen)
        if previous_content.content_type.model == 'quiz':
            quiz_instance = previous_content.item

            # Verificar si el alumno tiene algún intento aprobado para este examen
            has_passed = QuizAttempt.objects.filter(
                student=student,
                quiz=quiz_instance,
                passed=True
            ).exists()

            if not has_passed:
                return False  # Acceso bloqueado: Hay un examen previo sin aprobar

    return True  # Acceso concedido
