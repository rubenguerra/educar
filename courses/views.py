from django.shortcuts import redirect, get_object_or_404, render
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.generic.base import TemplateResponseMixin, View
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.forms.models import modelform_factory
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Count
from django.apps import apps
from django.core.cache import cache
from openai import OpenAI
from braces.views import CsrfExemptMixin, JsonRequestResponseMixin
from .models import Course, Module, Content, Subject, CourseAnalytics
from .forms import ModuleFormSet
from students.models import ChatMessage
from students.forms import CourseEnrollForm


class OwnerMixin(object):

    """Filtra los QuerySets para asegurar que el usuario opere solo en sus registros."""
    def get_queryset(self):
        return super().get_queryset().filter(owner=self.request.user)


class OwnerEditMixin(object):
    """Asigna automáticamente al usuario logueado como dueño del objeto al guardar."""
    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class OwnerCourseMixin(OwnerMixin, LoginRequiredMixin, PermissionRequiredMixin):
    model = Course
    fields = ['subject', 'title', 'slug', 'overview']
    success_url = reverse_lazy('manage_course_list')


class OwnerCourseEditMixin(OwnerCourseMixin, OwnerEditMixin):
    template_name = 'courses/manage/course/form.html'


# --- VISTAS DEL PANEL DE CONTROL DEL PROFESOR ---
class ManageCourseListView(OwnerCourseMixin, ListView):
    template_name = 'courses/manage/course/list.html'
    permission_required = 'courses.view_course'


class CourseCreateView(OwnerCourseEditMixin, CreateView):
    permission_required = 'courses.add_course'


class CourseUpdateView(OwnerCourseEditMixin, UpdateView):
    permission_required = 'courses.change_course'


class CourseDeleteView(OwnerCourseMixin, DeleteView):
    template_name = 'courses/manage/course/delete.html'
    permission_required = 'courses.delete_course'


# --- GESTIÓN DE MÓDULOS DE UN CURSO ---
class CourseModuleUpdateView(TemplateResponseMixin, View):
    template_name = 'courses/manage/module/formset.html'
    course = None

    def get_formset(self, data=None):
        return ModuleFormSet(instance=self.course, data=data)

    def dispatch(self, request, pk):
        self.course = get_object_or_404(Course, id=pk, owner=request.user)
        return super().dispatch(request, pk)

    def get(self, request, *args, **kwargs):
        return self.render_to_response({'course': self.course,
                                        'formset': self.get_formset()})

    def post(self, request, *args, **kwargs):
        formset = self.get_formset(data=request.POST)
        if formset.is_valid():
            formset.save()
            return redirect('manage_course_list')
        return self.render_to_response({'course': self.course,
                                        'formset': formset})


# --- GESTIÓN DINÁMICA DE CONTENIDOS (TEXTO, VIDEO, ETC.) ---
class ContentCreateUpdateView(TemplateResponseMixin, View):
    module = None
    model = None
    obj = None
    template_name = 'courses/manage/content/form.html'

    def get_model(self, model_name):
        allowed_models = Content._meta.get_field('content_type').remote_field.limit_choices_to['model__in']
        if model_name in allowed_models:
            return apps.get_model(app_label='courses', model_name=model_name)
        return None

    def get_form(self, model, *args, **kwargs):
        Form = modelform_factory(model, exclude=['owner', 'order', 'created', 'updated'])
        return Form(*args, **kwargs)

    def dispatch(self, request, module_id, model_name, id=None):
        self.module = get_object_or_404(Module, id=module_id, course__owner=request.user)
        self.model = self.get_model(model_name)
        if id:
            self.obj = get_object_or_404(self.model, id=id, owner=request.user)
        return super().dispatch(request, module_id, model_name, id)

    def get(self, request, module_id, model_name, id=None):
        form = self.get_form(self.model, instance=self.obj)
        return self.render_to_response({'form': form, 'object': self.obj})

    def post(self, request, module_id, model_name, id=None):
        form = self.get_form(self.model, instance=self.obj, data=request.POST, files=request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.owner = request.user
            obj.save()
            if not id:
                Content.objects.create(module=self.module, item=obj)
            return redirect('module_content_list', self.module.id)
        return self.render_to_response({'form': form, 'object': self.obj})


class ContentDeleteView(View):
    def post(self, request, id):
        content = get_object_or_404(Content, id=id, module__course__owner=request.user)
        module = content.module
        content.item.delete()
        content.delete()
        return redirect('module_content_list', module.id)


class ModuleContentListView(TemplateResponseMixin, View):
    template_name = 'courses/manage/module/content_list.html'

    def get(self, request, module_id):
        module = get_object_or_404(Module, id=module_id, course__owner=request.user)
        return self.render_to_response({'module': module})


class ModuleOrderView(CsrfExemptMixin, JsonRequestResponseMixin, View):
    def post(self, request):
        for id, order in self.request_json.items():
            Module.objects.filter(id=id, course__owner=request.user).update(order=order)
        return self.render_json_response({'saved': 'OK'})


class ContentOrderView(CsrfExemptMixin, JsonRequestResponseMixin, View):
    def post(self, request):
        for id, order in self.request_json.items():
            Content.objects.filter(id=id, module__course__owner=request.user).update(order=order)
        return self.render_json_response({'saved': 'OK'})


# --- VISTAS PÚBLICAS (ESTUDIANTES Y CATÁLOGO) ---
class CourseListView(TemplateResponseMixin, View):
    template_name = 'courses/course/list.html'

    def get(self, request, subject=None):

        subjects = cache.get('all_subjects')
        if not subjects:
            subjects = Subject.objects.annotate(total_courses=Count('courses'))
            cache.set('all_subjects', subjects)
        all_courses = Course.objects.with_modules_count()
        if subject:
            subject = get_object_or_404(Subject, slug=subject)
            key = f'subject_{subject.id}_courses'
            courses = cache.get(key)
            if not courses:
                courses = all_courses.filter(subject=subject)
                cache.set(key, courses)
        else:
            courses = cache.get('all_courses')
            if not courses:
                courses = all_courses
                cache.set('all_courses', courses)

        return self.render_to_response({'subjects': subjects, 'subject': subject, 'courses': courses})


class CourseDetailView(DetailView):
    model = Course
    template_name = 'courses/course/detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['enroll_form'] = CourseEnrollForm(initial={'course': self.object})
        return context


@login_required
def generate_course_ai_analytics(request, course_id):
    course = get_object_or_404(Course, id=course_id, owner=request.user)

    latest_report = course.ai_analytics.first()

    if request.method == 'POST':
        chat_logs = ChatMessage.objects.filter(course=course, sender_role='user').order_by('-timestamp')[:200]
        total_logs = chat_logs.count()

        if total_logs < 5:
            messages.warning(request, "Se requieren al menos 5 consultas de los alumnos en el chat para poder generar un análisis de patrones válido.")
            return redirect('courses:course_ai_analytics', course.id)
        compiled_questions = ""
        for log in reversed(chat_logs):
            compiled_questions += f'- Estudiante: {log.message}\n'

        try:
            client = OpenAI()

            prompt_analisis = (
                f"Actúas como un Consultor Analítico de Datos de Aprendizaje (Learning Analytics) experto.\n"
                f"Se te provee una lista de las consultas reales que los estudiantes le han hecho al tutor de IA dentro del curso '{course.title}'.\n\n"
                f"TU TAREA:\n"
                f"Analiza de forma rigurosa los textos, identifica patrones y redacta un informe ejecutivo estructurado en español dirigido al profesor del curso. "
                f"El informe DEBE estar formateado en Markdown limpio y contener exactamente estas secciones:\n"
                f"1. ### 📈 Resumen Ejecutivo: Breve diagnóstico del estado de dudas general.\n"
                f"2. ### 🔍 Las 3 Dudas o Vacíos Teóricos Más Comunes: Agrupa los mensajes en tres grandes temas recurrentes y explica por qué están confundidos.\n"
                f"3. ### 💡 Recomendaciones Pedagógicas Clave: Acciones concretas que el profesor puede tomar en su próxima clase o material para mitigar estas dudas.\n"
                f"4. ### ❓ Frases o Preguntas Clave: Cita textualmente 2 o 3 dudas de los alumnos que reflejen perfectamente la confusión colectiva.\n\n"
                f"LISTA DE CONSULTAS DE LOS ALUMNOS:\n{compiled_questions}"
            )
            response = client.chat.completions.create(
                model='gpt-4o-mini', messages=[{'role': 'user', 'content': prompt_analisis}], temperature=0.3, max_tokens=1000
            )

            ai_report = response.choices.message.content.strip()

            latest_report = CourseAnalytics.objects.create(course=course,
                                                           generated_by=request.user,
                                                           report_content=ai_report,
                                                           total_messages_analized=total_logs)
            messages.success(request, "¡Informe analítico de IA actualizado con éxito en base a los chats recientes!")
        except Exception as e:
            messages.error(request, f"Error de comunicación con la IA al compilar el reporte: {str(e)}")

        return redirect('courses:course_ai_analytics', course.id)
    return render(request, 'courses/manage/analytics/report.html',
                  {'course':course, 'report': latest_report})