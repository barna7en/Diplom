from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from .views import CommentCreateView, LikeCreateView, PostViewSet

router = DefaultRouter()
router.register(r'posts', PostViewSet, basename='post')

urlpatterns = [
    # Выдача токена аутентификации DRF (логин и пароль пользователя Django)
    path('token/', obtain_auth_token, name='api-token'),
    path('', include(router.urls)),
    path(
        'posts/<int:post_id>/comments/',
        CommentCreateView.as_view(),
        name='post-comment-create',
    ),
    path(
        'posts/<int:post_id>/likes/',
        LikeCreateView.as_view(),
        name='post-like-create',
    ),
]
