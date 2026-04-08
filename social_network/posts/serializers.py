from rest_framework import serializers

from .models import Comment, Post


class CommentSerializer(serializers.ModelSerializer):
    """Комментарий: вывод автора, текста и даты (автор задаётся при сохранении на уровне представления)."""

    class Meta:
        model = Comment
        fields = ('author', 'text', 'created_at')
        read_only_fields = ('author', 'created_at')


class PostListSerializer(serializers.ModelSerializer):
    """Пост в списке: без вложенных комментариев и без счётчика лайков."""

    class Meta:
        model = Post
        fields = ('id', 'text', 'image', 'created_at')
        read_only_fields = ('created_at',)


class PostDetailSerializer(serializers.ModelSerializer):
    """Детали поста: вложенные комментарии и число лайков по связи likes."""

    comments = CommentSerializer(many=True, read_only=True)
    likes_count = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = (
            'id',
            'text',
            'image',
            'created_at',
            'comments',
            'likes_count',
        )
        read_only_fields = ('created_at', 'likes_count')

    def get_likes_count(self, obj):
        # Количество записей Like для поста (related_name='likes')
        return obj.likes.count()


class PostWriteSerializer(serializers.ModelSerializer):
    """Создание/редактирование: только поля, разрешённые в теле запроса; автор подставляется из request.user."""

    class Meta:
        model = Post
        fields = ('text', 'image')


# Имя из формулировки этапа: детальный вывод поста
PostSerializer = PostDetailSerializer
