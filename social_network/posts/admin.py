from django.contrib import admin

from .models import Comment, Like, Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    # Список: идентификатор, автор, краткий текст, дата создания
    list_display = ('id', 'author', 'text_preview', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('text', 'author__username')
    raw_id_fields = ('author',)
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

    @admin.display(description='текст (кратко)')
    def text_preview(self, obj):
        # Усечённый текст для удобного просмотра в списке админки
        if not obj.pk:
            return ''
        t = obj.text or ''
        return (t[:50] + '…') if len(t) > 50 else t


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'post', 'author', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('text', 'author__username', 'post__text')
    raw_id_fields = ('author', 'post')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ('id', 'post', 'user')
    list_filter = ('post', 'user')
    search_fields = ('user__username', 'post__text')
    raw_id_fields = ('user', 'post')
