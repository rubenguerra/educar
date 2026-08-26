from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic.edit import CreateView, FormView
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from .forms import CourseEnrollForm
from courses.models import Content, Course, Quiz, Question, Choice
from .models import StudentProgress, QuizAttempt, QuizAttemptAnswer
from .utils import can_access_content


class StudentRegistrationView(CreateView):
    template_name = 'students/student/registration.html'
    form_class = UserCreationForm
    success_url = reverse_lazy('student_course_list')

    def form_valid(self, form):
        response = super().form_valid(form)

        login(self.request, self.object)
        return response


class StudentEnrollCourseView(LoginRequiredMixin, FormView):
    course = None
    form_class = CourseEnrollForm

    def form_valid(self, form):
        self.course = form.cleaned_data['course']
        self.course.students.add(self.request.user)
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('student_course_detail',
                            args=[self.course.id])


class StudentCourseListView(LoginRequiredMixin, ListView):
    model = Course
    template_name = 'students/course/list.html'

    def get_queryset(self):
        qs = Course.objects.for_student(self.request.user).with_modules_count()
        return qs.select_related('subject')


class StudentCourseDetailView(LoginRequiredMixin, DetailView):
    model = Course
    template_name = 'students/course/detail.html'
    context_object_name = 'course'

    def get_queryset(self):
        qs = Course.objects.for_student(self.request.user)
        return qs.prefetch_related('modules', 'modules__contents')

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        content_id = request.GET.get('content')
        if content_id:
            try:
                requested_content = Content.objects.get(id=content_id, module__course=self.object)
                if not can_access_content(request.user, requested_content):
                    messages.error(
                        request,
                        f"🔒 Contenido bloqueado. Debes aprobar los exámenes previos de este módulo para continuar."
                    )
                    return redirect('students:student_course_detail', self.object.id)
            except Content.DoesNotExist:
                pass
        return super().get(request, *args, **kwargs )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        progress, _ = StudentProgress.objects.get_or_created(
            student=self.request.user,
            course=self.object
        )

        context['completed_contents'] = progress.completed_contents.all()
        context['quiz_attempts'] = QuizAttempt.objects.filter(
            student=self.request.user,
            quiz__module__course=self.object
        ).select_related('quiz').order_by('-taken_at')

        return context


@login_required
def student_submit_quiz(request, quiz_id):
    """
    Procesa el envío de un examen por parte del estudiante,
    calcula la nota y registra el progreso/calificación.
    """
    if request.method != 'POST':
        return redirect('students:student_course_list')

    quiz = get_object_or_404(Quiz, id=quiz_id)
    questions = quiz.questions.prefetch_related('choices')
    total_questions = questions.count()

    if total_questions == 0:
        messages.error(request, "Este examen no tiene preguntas configuradas.")
        return redirect('students:student_course_detail', quiz.module.course.id)

    correct_answers_count = 0
    answers_to_create = []

    attempt = QuizAttempt(student=request.user,
                          quiz=quiz,
                          total_questions=total_questions,
                          score=0.0)

    for question in questions:
        field_name = f'question_{question.id}'
        selected_choice_id = request.POST.get(field_name)
        selected_choice = None

        if selected_choice_id:
            try:
                selected_choice = question.choices.get(id=selected_choice_id)
                if selected_choice.is_correct:
                    correct_answers_count += 1
            except Choice.DoesNotExist:
                pass

        answers_to_create.append(QuizAttemptAnswer(
            attempt=attempt,
            question=question,
            selected_choice=selected_choice
        ))

    score = round((correct_answers_count / total_questions) * 10.0, 2)
    percentage = round((correct_answers_count / total_questions) * 100, 1)
    is_passed = percentage >= 60.0

    attempt.score = score
    attempt.correct_answers = correct_answers_count
    attempt.passed = is_passed
    attempt.save()

    for answer in answers_to_create:
        answer.attempt_id = attempt.id
    QuizAttemptAnswer.objects.bulk_create(answers_to_create)

    course = quiz.module.course
    progress, _ = StudentProgress.objects.get_or_created(student=request.user,
                                                         course=course)
    content_object = quiz.contents.first()
    if is_passed and content_object:
        progress.completed_contents.add(content_object)

    QuizAttempt.objects.create(student=request.user,
                               quiz=quiz,
                               score=score,
                               correct_answers = correct_answers_count,
                               total_questions=total_questions,
                               passed=is_passed)

    course = quiz.module.course
    progress, created = StudentProgress.objects.get_or_created(
        student=request.user,
        course=course
    )

    # Resultado
    content_object = quiz.contents.first()
    if is_passed and content_object:
        progress.completed_contents.add(content_object)

    return redirect('students:quiz_attempt_detail', attempt.id)


@login_required
def quiz_attempt_detail(request, attempt_id):
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, student=request.user)
    answers = attempt.answers.select_related('question',
                                             'selected_choice').prefetch_related('question_choices')
    return render(request, 'students/quiz/attempt_detail.html',{
        'attempt': attempt,
        'answers': answers,
        'course': attempt.quiz.module.course
    })