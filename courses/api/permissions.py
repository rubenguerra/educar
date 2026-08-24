from rest_framework.permissions import BasePermission


class IsEnrolled(BasePermission):
    """
        Permiso personalizado para asegurar que solo los estudiantes inscritos
        puedan acceder a los contenidos privados del curso.
    """
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user in obj.students.all()