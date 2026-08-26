from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from courses.models import Course, Content, Quiz, Question, Choice


class StudentProgress(models.Model):
    student = models.ForeignKey( settings.AUTH_USER_MODEL,
                                 related_name='course_progress',
                                 on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    completed_contents = models.ManyToManyField(Content, blank=True, related_name='completed_by')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Progreso del Estudiante'
        verbose_name_plural = 'Progresos de los Estudiantes'
        unique_together = ('student', 'course')

    def __str__(self):
        return f"{self.student.username} - {self.course.title}"


class QuizAttempt(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL,
                                related_name='quiz_attempts',
                                on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, related_name='attemps',
                             on_delete=models.CASCADE)
    score = models.DecimalField(max_digits=4,
                                decimal_places=2,
                                validators=[MinValueValidator(0.0), MaxValueValidator(10.0)],
                                help_text='Calificación obtenido en escala de 0 a 10')
    correct_answers = models.PositiveIntegerField(
        help_text='Número de respuestas correctas'
    )
    total_questions = models.PositiveIntegerField(
        help_text='Total de preguntas en el examen al momento de responder'
    )
    passed = models.BooleanField(default=False,
                                 help_text='Indica si el estudiante superó la nota mínima')
    taken_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Intento de examen'
        verbose_name_plural = 'Intentos de exámenes'
        ordering = ['-taken_at']

    def __str__(self):
        return f'{self.student.username} - {self.quiz.title} ({self.score}/10)'


class QuizAttemptAnswer(models.Model):
    """
    Almacena la opción específica que selecciona el alumno para cada pregunta
    """
    attempt = models.ForeignKey(
        QuizAttempt,
        related_name='answers',
        on_delete=models.CASCADE
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE
    )
    selected_choice = models.ForeignKey(
        Choice,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = 'Respuesta de Intento'
        verbose_name_plural = 'Respuestas de Intentos'

    def __str__(self):
        return f'{self.attempt.student.username} - {self.question}: {self.selected_choice}'