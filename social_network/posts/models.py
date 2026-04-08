from django.contrib.auth import get_user_model
from django.db import models


User = get_user_model()


class Post(models.Model):
    """Публикация: текст, изображение и автор."""

    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='posts',
        verbose_name='автор',
    )
    text = models.TextField(verbose_name='текст')
    image = models.ImageField(upload_to='posts/', verbose_name='изображение')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='создан')

    class Meta:
        verbose_name = 'публикация'
        verbose_name_plural = 'публикации'
        ordering = ('-created_at',)

    def __str__(self):
        preview = (self.text[:50] + '…') if len(self.text) > 50 else self.text
        return f'Пост #{self.pk} — {preview}'


# для доп. задания
# class PostImage(models.Model):
#     ...


class Comment(models.Model):
    """Комментарий к публикации."""

    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='authored_comments',
        verbose_name='автор',
    )
    post = models.ForeignKey(
        'Post',
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name='публикация',
    )
    text = models.TextField(verbose_name='текст')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='создан')

    class Meta:
        verbose_name = 'комментарий'
        verbose_name_plural = 'комментарии'
        ordering = ('created_at',)

    def __str__(self):
        return f'Комментарий #{self.pk} к посту #{self.post_id}'


class Like(models.Model):
    """Лайк пользователя к публикации (один пользователь — один лайк на пост)."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='likes',
        verbose_name='пользователь',
    )
    post = models.ForeignKey(
        'Post',
        on_delete=models.CASCADE,
        related_name='likes',
        verbose_name='публикация',
    )

    class Meta:
        verbose_name = 'лайк'
        verbose_name_plural = 'лайки'
        ordering = ('id',)
        constraints = [
            models.UniqueConstraint(
                fields=('user', 'post'),
                name='unique_like_user_post',
            ),
        ]

    def __str__(self):
        return f'Лайк пользователя {self.user_id} на пост #{self.post_id}'
