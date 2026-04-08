from django.shortcuts import get_object_or_404
from rest_framework import generics, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Like, Post
from .permissions import IsAuthorOrReadOnly
from .serializers import CommentSerializer, PostDetailSerializer, PostListSerializer, PostWriteSerializer


class PostViewSet(viewsets.ModelViewSet):
    """Список/детали постов для всех; создание — только с токеном; правка/удаление — только автор."""

    queryset = Post.objects.all()

    def get_queryset(self):
        qs = Post.objects.all().order_by('-created_at')
        if self.action == 'retrieve':
            return qs.prefetch_related('comments__author', 'likes')
        return qs.select_related('author')

    def get_serializer_class(self):
        if self.action == 'list':
            return PostListSerializer
        if self.action == 'retrieve':
            return PostDetailSerializer
        return PostWriteSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        if self.action == 'create':
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsAuthorOrReadOnly()]

    def perform_create(self, serializer):
        # Автор поста всегда из учётной записи по токену, не из тела запроса
        serializer.save(author=self.request.user)

    def create(self, request, *args, **kwargs):
        # Вход — PostWriteSerializer; в ответе — полная форма поста (как при GET детали)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        instance = serializer.instance
        detail = PostDetailSerializer(instance, context=self.get_serializer_context())
        headers = self.get_success_headers(detail.data)
        return Response(detail.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        instance = serializer.instance
        detail = PostDetailSerializer(instance, context=self.get_serializer_context())
        return Response(detail.data)


class CommentCreateView(generics.CreateAPIView):
    """Добавление комментария к посту (только для аутентифицированных пользователей)."""

    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated]

    def get_post(self):
        return get_object_or_404(Post, pk=self.kwargs['post_id'])

    def perform_create(self, serializer):
        # Пост из post_id в URL, автор из токена; поля post/author из тела не используются
        serializer.save(author=self.request.user, post=self.get_post())


class LikeCreateView(APIView):
    """Лайк поста: POST — поставить; DELETE — снять свой лайк. Пользователь только из токена, пост — из URL."""

    permission_classes = [IsAuthenticated]

    def post(self, request, post_id):
        post = get_object_or_404(Post, pk=post_id)
        # Пара user/post задаётся только из запроса и пути; дубликат обрабатывается без ошибки БД
        _like, created = Like.objects.get_or_create(user=request.user, post=post)
        return Response(
            {'created': created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, post_id):
        post = get_object_or_404(Post, pk=post_id)
        # Удаляется только лайк текущего пользователя на этот пост
        deleted_count, _ = Like.objects.filter(user=request.user, post=post).delete()
        if deleted_count == 0:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response({'deleted': True}, status=status.HTTP_200_OK)
