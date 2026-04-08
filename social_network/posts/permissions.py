from rest_framework import permissions


class IsAuthorOrReadOnly(permissions.BasePermission):
    """
    Чтение (GET, HEAD, OPTIONS) разрешено всем.
    Изменение и удаление — только если текущий пользователь — автор объекта.
    """

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        author = getattr(obj, 'author', None)
        if author is None:
            return False
        return author == request.user
