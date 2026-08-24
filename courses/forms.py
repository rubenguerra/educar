from django import forms
from django.forms.models import inlineformset_factory
from .models import Course, Module


# Clase que da estilos a los formularios
class BaseModuleForm(forms.ModelForm):
    """
    Formulario base para Module.
    """
    class Meta:
        model = Module
        fields = ['title', 'description']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control font-weight-bold',
                'placeholder': 'Ej. Introducción al curso'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe brevemente lo que se aprenderá en este módulo... '
            }),

        }


ModuleFormSet = inlineformset_factory(Course,
                                      Module,
                                      form=BaseModuleForm,
                                      fields=['title', 'description'],
                                      extra=1,
                                      can_delete=True)
