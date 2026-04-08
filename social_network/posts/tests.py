import time
from io import BytesIO

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import resolve, reverse
from PIL import Image
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .admin import CommentAdmin, LikeAdmin, PostAdmin
from .models import Comment, Like, Post
from .serializers import (
    CommentSerializer,
    PostDetailSerializer,
    PostListSerializer,
    PostWriteSerializer,
)

User = get_user_model()


def _tiny_png():
    """Валидное изображение 1×1 для ImageField в тестах."""
    buf = BytesIO()
    Image.new('RGB', (1, 1), color='white').save(buf, format='PNG')
    buf.seek(0)
    return SimpleUploadedFile('test.png', buf.read(), content_type='image/png')


class PostModelTests(TestCase):
    """Создание поста и базовые поля."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='author1',
            password='test-pass-123',
        )

    def test_post_can_be_created(self):
        post = Post.objects.create(
            author=self.user,
            text='Текст публикации',
            image=_tiny_png(),
        )
        self.assertIsNotNone(post.pk)
        self.assertEqual(post.author, self.user)
        self.assertEqual(post.text, 'Текст публикации')
        self.assertTrue(post.image.name)
        self.assertIsNotNone(post.created_at)

    def test_post_related_name_comments_and_likes(self):
        post = Post.objects.create(
            author=self.user,
            text='Пост',
            image=_tiny_png(),
        )
        other = User.objects.create_user(username='other', password='x')
        Comment.objects.create(author=other, post=post, text='Привет')
        Like.objects.create(user=other, post=post)

        self.assertEqual(post.comments.count(), 1)
        self.assertEqual(post.likes.count(), 1)
        self.assertEqual(post.comments.first().text, 'Привет')

    def test_post_ordering_newest_first(self):
        p1 = Post.objects.create(
            author=self.user,
            text='Первый',
            image=_tiny_png(),
        )
        time.sleep(0.02)
        p2 = Post.objects.create(
            author=self.user,
            text='Второй',
            image=_tiny_png(),
        )
        ids = list(Post.objects.values_list('id', flat=True))
        self.assertEqual(ids[0], p2.id)
        self.assertEqual(ids[1], p1.id)


class CommentModelTests(TestCase):
    """Комментарий привязан к посту."""

    def setUp(self):
        self.user = User.objects.create_user(username='u', password='p')
        self.post = Post.objects.create(
            author=self.user,
            text='Пост',
            image=_tiny_png(),
        )

    def test_comment_can_be_created_and_linked_to_post(self):
        c = Comment.objects.create(
            author=self.user,
            post=self.post,
            text='Комментарий',
        )
        self.assertEqual(c.post_id, self.post.id)
        self.assertIn(c, self.post.comments.all())

    def test_comment_ordering_oldest_first(self):
        c1 = Comment.objects.create(
            author=self.user,
            post=self.post,
            text='Первый',
        )
        time.sleep(0.02)
        c2 = Comment.objects.create(
            author=self.user,
            post=self.post,
            text='Второй',
        )
        texts = list(self.post.comments.values_list('text', flat=True))
        self.assertEqual(texts, ['Первый', 'Второй'])


class LikeModelTests(TestCase):
    """Лайки и уникальность пары пользователь–пост."""

    def setUp(self):
        self.user = User.objects.create_user(username='liker', password='p')
        self.post = Post.objects.create(
            author=self.user,
            text='Пост',
            image=_tiny_png(),
        )

    def test_like_can_be_created(self):
        like = Like.objects.create(user=self.user, post=self.post)
        self.assertIsNotNone(like.pk)

    def test_duplicate_like_same_user_post_rejected(self):
        Like.objects.create(user=self.user, post=self.post)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Like.objects.create(user=self.user, post=self.post)

    def test_like_ordering_by_id(self):
        u2 = User.objects.create_user(username='u2', password='p')
        l1 = Like.objects.create(user=self.user, post=self.post)
        l2 = Like.objects.create(user=u2, post=self.post)
        ids = list(Like.objects.values_list('id', flat=True))
        self.assertEqual(ids, [l1.id, l2.id])


class PostsAdminTests(TestCase):
    """Проверка регистрации моделей в стандартной админке Django (этап 4)."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin_stage4',
            email='admin_stage4@example.com',
            password='secret-admin-pass',
        )
        self.author = User.objects.create_user(username='author_sn', password='p')
        self.post = Post.objects.create(
            author=self.author,
            text='Текст для поиска в админке',
            image=_tiny_png(),
        )
        self.client = Client()
        self.client.force_login(self.superuser)

    def test_admin_registry_uses_expected_modeladmin(self):
        # Модели зарегистрированы с нужными классами ModelAdmin
        self.assertIsInstance(admin.site._registry[Post], PostAdmin)
        self.assertIsInstance(admin.site._registry[Comment], CommentAdmin)
        self.assertIsInstance(admin.site._registry[Like], LikeAdmin)

    def test_changelist_and_add_pages_return_200(self):
        # Списки и формы добавления открываются суперпользователем
        models_meta = (
            ('posts', 'post'),
            ('posts', 'comment'),
            ('posts', 'like'),
        )
        for app_label, model_name in models_meta:
            for view in ('changelist', 'add'):
                url = reverse(f'admin:{app_label}_{model_name}_{view}')
                response = self.client.get(url)
                self.assertEqual(
                    response.status_code,
                    200,
                    msg=f'Ожидался 200 для {url}',
                )

    def test_post_comment_like_visible_after_orm_create(self):
        # Создание через ORM совместимо с отображением в админке (лайки только просмотр/список)
        Comment.objects.create(
            author=self.author,
            post=self.post,
            text='Комментарий в админке',
        )
        Like.objects.create(user=self.author, post=self.post)

        post_cl = self.client.get(reverse('admin:posts_post_changelist'))
        self.assertEqual(post_cl.status_code, 200)
        self.assertContains(post_cl, 'Текст для поиска в админке')

        comment_cl = self.client.get(reverse('admin:posts_comment_changelist'))
        self.assertEqual(comment_cl.status_code, 200)
        # В списке комментариев видны автор и привязка к посту (list_display)
        self.assertContains(comment_cl, self.author.username)

        like_cl = self.client.get(reverse('admin:posts_like_changelist'))
        self.assertEqual(like_cl.status_code, 200)
        # В списке лайков отображается пользователь (list_display: user)
        self.assertContains(like_cl, self.author.username)


class SerializerTests(TestCase):
    """Проверка сериализаторов API (этап 5)."""

    def setUp(self):
        self.user = User.objects.create_user(username='ser_user', password='p')
        self.other = User.objects.create_user(username='ser_other', password='p')
        self.post = Post.objects.create(
            author=self.user,
            text='Текст поста',
            image=_tiny_png(),
        )

    def test_comment_serializer_output_fields(self):
        # В ответе есть автор, текст и дата создания
        comment = Comment.objects.create(
            author=self.other,
            post=self.post,
            text='Привет',
        )
        data = CommentSerializer(comment).data
        self.assertEqual(set(data.keys()), {'author', 'text', 'created_at'})
        self.assertEqual(data['author'], self.other.id)
        self.assertEqual(data['text'], 'Привет')
        self.assertIsNotNone(data['created_at'])

    def test_post_detail_includes_nested_comments_and_likes_count(self):
        Like.objects.create(user=self.user, post=self.post)
        Like.objects.create(user=self.other, post=self.post)
        Comment.objects.create(author=self.other, post=self.post, text='Один')
        Comment.objects.create(author=self.user, post=self.post, text='Два')

        data = PostDetailSerializer(self.post).data
        self.assertEqual(data['likes_count'], 2)
        self.assertEqual(len(data['comments']), 2)
        self.assertEqual({c['text'] for c in data['comments']}, {'Один', 'Два'})
        for c in data['comments']:
            self.assertIn('author', c)
            self.assertIn('created_at', c)

    def test_comment_serializer_read_only_author_and_created_at_on_write(self):
        # При записи поля author и created_at не попадают в validated_data
        payload = {
            'text': 'Новый',
            'author': self.other.id,
            'created_at': '2000-01-01T00:00:00Z',
        }
        serializer = CommentSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data.keys(), {'text'})

    def test_post_write_serializer_author_not_writable_and_allowed_fields_only(self):
        # Разрешены только text и image; author из входных данных не принимается
        self.assertEqual(set(PostWriteSerializer().fields.keys()), {'text', 'image'})
        payload = {
            'text': 'Обновление',
            'image': _tiny_png(),
            'author': self.other.id,
            'created_at': '2000-01-01T00:00:00Z',
        }
        serializer = PostWriteSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(set(serializer.validated_data.keys()), {'text', 'image'})
        self.assertNotIn('author', serializer.validated_data)
        self.assertNotIn('created_at', serializer.validated_data)

    def test_post_list_serializer_shape(self):
        # Список без комментариев и без likes_count
        data = PostListSerializer(self.post).data
        self.assertEqual(
            set(data.keys()),
            {'id', 'text', 'image', 'created_at'},
        )
        self.assertNotIn('comments', data)
        self.assertNotIn('likes_count', data)

    def test_post_write_created_at_not_in_fields(self):
        # created_at не входит в поля записи поста
        self.assertNotIn('created_at', PostWriteSerializer().fields)

    def test_post_detail_read_only_created_at_in_meta(self):
        # created_at помечен только для чтения в детальном сериализаторе
        field = PostDetailSerializer().fields['created_at']
        self.assertTrue(field.read_only)


class ApiPermissionsTests(TestCase):
    """Права доступа и аутентификация по токену (этап 6)."""

    def setUp(self):
        self.client = APIClient()
        self.author = User.objects.create_user(username='api_author', password='pw')
        self.other = User.objects.create_user(username='api_other', password='pw')
        self.post = Post.objects.create(
            author=self.author,
            text='Исходный текст',
            image=_tiny_png(),
        )
        self.author_token = Token.objects.create(user=self.author)
        self.other_token = Token.objects.create(user=self.other)

    def _auth(self, user):
        token = Token.objects.get(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def _clear_auth(self):
        self.client.credentials()

    def test_anonymous_cannot_create_post(self):
        self._clear_auth()
        response = self.client.post(
            reverse('post-list'),
            {'text': 'Новый', 'image': _tiny_png()},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_can_create_post_and_author_from_user(self):
        self._auth(self.author)
        evil = User.objects.create_user(username='evil_claim', password='x')
        response = self.client.post(
            reverse('post-list'),
            {
                'text': 'Создан по API',
                'image': _tiny_png(),
                'author': evil.pk,
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Post.objects.get(author=self.author, text='Создан по API')
        self.assertEqual(created.author_id, self.author.id)
        self.assertNotEqual(created.author_id, evil.id)

    def test_anonymous_cannot_update_or_delete_post(self):
        self._clear_auth()
        url = reverse('post-detail', kwargs={'pk': self.post.pk})
        self.assertEqual(
            self.client.patch(url, {'text': 'X'}, format='json').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_author_cannot_update_or_delete_post(self):
        self._auth(self.other)
        url = reverse('post-detail', kwargs={'pk': self.post.pk})
        self.assertEqual(
            self.client.patch(url, {'text': 'Чужой'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_403_FORBIDDEN)

    def test_author_can_update_and_delete_own_post(self):
        self._auth(self.author)
        url = reverse('post-detail', kwargs={'pk': self.post.pk})
        patch_resp = self.client.patch(url, {'text': 'Обновлено'}, format='json')
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        self.post.refresh_from_db()
        self.assertEqual(self.post.text, 'Обновлено')
        del_resp = self.client.delete(url)
        self.assertEqual(del_resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Post.objects.filter(pk=self.post.pk).exists())

    def test_anonymous_cannot_create_comment(self):
        self._clear_auth()
        url = reverse('post-comment-create', kwargs={'post_id': self.post.pk})
        response = self.client.post(url, {'text': 'Коммент'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_can_create_comment_author_from_user(self):
        # Автор комментария — владелец токена; поле author из JSON не подменяет владельца
        self._auth(self.other)
        url = reverse('post-comment-create', kwargs={'post_id': self.post.pk})
        before = Comment.objects.count()
        response = self.client.post(
            url,
            {'text': 'Мой коммент', 'author': self.author.pk},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Comment.objects.count(), before + 1)
        c = Comment.objects.latest('pk')
        self.assertEqual(c.author, self.other)
        self.assertEqual(c.post, self.post)
        self.assertEqual(c.text, 'Мой коммент')

    def test_anonymous_cannot_like(self):
        self._clear_auth()
        url = reverse('post-like-create', kwargs={'post_id': self.post.pk})
        self.assertEqual(self.client.post(url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_like_and_duplicate_safe(self):
        url = reverse('post-like-create', kwargs={'post_id': self.post.pk})
        self._auth(self.author)
        r1 = self.client.post(url)
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertTrue(r1.data.get('created'))
        self.assertEqual(self.post.likes.filter(user=self.author).count(), 1)
        r2 = self.client.post(url)
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertFalse(r2.data.get('created'))
        self.assertEqual(self.post.likes.filter(user=self.author).count(), 1)

    def test_like_user_from_token_not_payload(self):
        self._auth(self.other)
        url = reverse('post-like-create', kwargs={'post_id': self.post.pk})
        response = self.client.post(url, {'user': self.author.pk}, format='json')
        self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
        like = Like.objects.get(post=self.post, user=self.other)
        self.assertEqual(like.user_id, self.other.id)

    def test_list_and_detail_allow_anonymous(self):
        self._clear_auth()
        self.assertEqual(self.client.get(reverse('post-list')).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.get(reverse('post-detail', kwargs={'pk': self.post.pk})).status_code,
            status.HTTP_200_OK,
        )


class PostsApiCrudTests(TestCase):
    """CRUD постов по API (этап 7): список, деталь, создание, правка, удаление, валидация."""

    def setUp(self):
        self.client = APIClient()
        self.author = User.objects.create_user(username='crud_author', password='pw')
        self.other = User.objects.create_user(username='crud_other', password='pw')
        self.post = Post.objects.create(
            author=self.author,
            text='Текст для списка и детали',
            image=_tiny_png(),
        )
        self.author_token = Token.objects.create(user=self.author)
        self.other_token = Token.objects.create(user=self.other)

    def _auth(self, user):
        token = Token.objects.get(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def _clear_auth(self):
        self.client.credentials()

    def test_anonymous_get_posts_list_returns_200_and_includes_posts(self):
        self._clear_auth()
        p2 = Post.objects.create(author=self.other, text='Второй', image=_tiny_png())
        r = self.client.get(reverse('post-list'))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        ids = {item['id'] for item in r.data}
        self.assertIn(self.post.id, ids)
        self.assertIn(p2.id, ids)

    def test_anonymous_get_post_detail_returns_200_with_expected_fields(self):
        self._clear_auth()
        r = self.client.get(reverse('post-detail', kwargs={'pk': self.post.pk}))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        for key in ('id', 'text', 'image', 'created_at', 'comments', 'likes_count'):
            self.assertIn(key, r.data)
        self.assertEqual(r.data['id'], self.post.id)
        self.assertEqual(r.data['text'], self.post.text)
        self.assertEqual(r.data['likes_count'], 0)

    def test_get_post_detail_missing_returns_404(self):
        self._clear_auth()
        missing_id = Post.objects.order_by('-id').values_list('id', flat=True).first() or 0
        missing_id += 9999
        r = self.client.get(reverse('post-detail', kwargs={'pk': missing_id}))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_authenticated_post_create_response_uses_detail_shape(self):
        self._auth(self.author)
        r = self.client.post(
            reverse('post-list'),
            {'text': 'Новый пост', 'image': _tiny_png()},
            format='multipart',
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertIn('comments', r.data)
        self.assertIn('likes_count', r.data)
        self.assertEqual(r.data['text'], 'Новый пост')

    def test_anonymous_put_rejected(self):
        self._clear_auth()
        url = reverse('post-detail', kwargs={'pk': self.post.pk})
        self.assertEqual(
            self.client.put(
                url,
                {'text': 'Полная замена', 'image': _tiny_png()},
                format='multipart',
            ).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_non_author_put_rejected_author_put_succeeds(self):
        url = reverse('post-detail', kwargs={'pk': self.post.pk})
        self._auth(self.other)
        self.assertEqual(
            self.client.put(
                url,
                {'text': 'Чужой PUT', 'image': _tiny_png()},
                format='multipart',
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self._auth(self.author)
        new_img = _tiny_png()
        r = self.client.put(
            url,
            {'text': 'Обновлено PUT', 'image': new_img},
            format='multipart',
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.post.refresh_from_db()
        self.assertEqual(self.post.text, 'Обновлено PUT')

    def test_invalid_post_payload_returns_400_not_500(self):
        self._auth(self.author)
        # Без обязательного изображения при создании
        r = self.client.post(reverse('post-list'), {'text': 'Без картинки'}, format='multipart')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(r.status_code >= 500)


class CommentsApiStage8Tests(TestCase):
    """API комментариев к посту (этап 8): создание по post_id в URL, без подмены автора/поста из тела."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='c8_user', password='pw')
        self.other = User.objects.create_user(username='c8_other', password='pw')
        self.post_a = Post.objects.create(
            author=self.user,
            text='Пост A',
            image=_tiny_png(),
        )
        self.post_b = Post.objects.create(
            author=self.user,
            text='Пост B',
            image=_tiny_png(),
        )
        Token.objects.create(user=self.user)

    def _auth(self):
        token = Token.objects.get(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def _clear_auth(self):
        self.client.credentials()

    def test_anonymous_post_comment_rejected(self):
        self._clear_auth()
        url = reverse('post-comment-create', kwargs={'post_id': self.post_a.pk})
        r = self.client.post(url, {'text': 'Коммент'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_post_comment_succeeds_and_links_post_and_author(self):
        self._auth()
        url = reverse('post-comment-create', kwargs={'post_id': self.post_a.pk})
        r = self.client.post(url, {'text': 'Этап 8'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        c = Comment.objects.latest('pk')
        self.assertEqual(c.post_id, self.post_a.id)
        self.assertEqual(c.author, self.user)
        self.assertEqual(c.text, 'Этап 8')
        self.assertEqual(r.data.get('author'), self.user.id)
        self.assertEqual(r.data.get('text'), 'Этап 8')

    def test_payload_author_does_not_override_request_user(self):
        self._auth()
        url = reverse('post-comment-create', kwargs={'post_id': self.post_a.pk})
        r = self.client.post(
            url,
            {'text': 'X', 'author': self.other.pk},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        c = Comment.objects.latest('pk')
        self.assertEqual(c.author_id, self.user.id)
        self.assertNotEqual(c.author_id, self.other.id)

    def test_payload_post_does_not_override_url_post_id(self):
        # В теле передан другой пост — комментарий всё равно к посту из пути
        self._auth()
        url = reverse('post-comment-create', kwargs={'post_id': self.post_a.pk})
        r = self.client.post(
            url,
            {'text': 'Привязка по URL', 'post': self.post_b.pk},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        c = Comment.objects.latest('pk')
        self.assertEqual(c.post_id, self.post_a.id)
        self.assertNotEqual(c.post_id, self.post_b.id)

    def test_post_comment_missing_post_returns_404(self):
        self._auth()
        missing_id = Post.objects.order_by('-id').values_list('id', flat=True).first() or 0
        missing_id += 9999
        url = reverse('post-comment-create', kwargs={'post_id': missing_id})
        r = self.client.post(url, {'text': 'Некуда'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_post_detail_still_includes_nested_comments_after_api_comment(self):
        # Регрессия: деталь поста по-прежнему отдаёт вложенные комментарии
        self._auth()
        self.client.post(
            reverse('post-comment-create', kwargs={'post_id': self.post_a.pk}),
            {'text': 'Через API'},
            format='json',
        )
        self._clear_auth()
        r = self.client.get(reverse('post-detail', kwargs={'pk': self.post_a.pk}))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        texts = {item['text'] for item in r.data['comments']}
        self.assertIn('Через API', texts)

    def test_posts_list_and_permissions_still_work(self):
        # Регрессия: список постов и права на создание поста без регрессий
        self._clear_auth()
        self.assertEqual(self.client.get(reverse('post-list')).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.post(
                reverse('post-list'),
                {'text': 'Без токена', 'image': _tiny_png()},
                format='multipart',
            ).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


class LikesApiStage9Tests(TestCase):
    """API лайков (этап 9): POST/DELETE по post_id, защита от дубликатов, likes_count в детали поста."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='l9_user', password='pw')
        self.other = User.objects.create_user(username='l9_other', password='pw')
        self.post = Post.objects.create(
            author=self.user,
            text='Пост для лайков',
            image=_tiny_png(),
        )
        Token.objects.create(user=self.user)
        Token.objects.create(user=self.other)

    def _auth(self, user):
        token = Token.objects.get(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def _clear_auth(self):
        self.client.credentials()

    def _likes_url(self, post_pk):
        return reverse('post-like-create', kwargs={'post_id': post_pk})

    def test_anonymous_post_like_rejected(self):
        self._clear_auth()
        r = self.client.post(self._likes_url(self.post.pk))
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_post_like_succeeds_and_links_user_and_post(self):
        self._auth(self.user)
        r = self.client.post(self._likes_url(self.post.pk))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertTrue(r.data.get('created'))
        like = Like.objects.get(post=self.post, user=self.user)
        self.assertEqual(like.user_id, self.user.id)
        self.assertEqual(like.post_id, self.post.id)

    def test_post_like_missing_post_returns_404(self):
        self._auth(self.user)
        missing_id = Post.objects.order_by('-id').values_list('id', flat=True).first() or 0
        missing_id += 9999
        r = self.client.post(self._likes_url(missing_id))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_duplicate_post_like_no_second_row_and_no_500(self):
        self._auth(self.user)
        url = self._likes_url(self.post.pk)
        r1 = self.client.post(url)
        r2 = self.client.post(url)
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertFalse(r2.data.get('created'))
        self.assertFalse(r2.status_code >= 500)
        self.assertEqual(Like.objects.filter(user=self.user, post=self.post).count(), 1)

    def test_anonymous_delete_like_rejected(self):
        self._clear_auth()
        r = self.client.delete(self._likes_url(self.post.pk))
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_delete_removes_only_own_like(self):
        Like.objects.create(user=self.user, post=self.post)
        Like.objects.create(user=self.other, post=self.post)
        self._auth(self.user)
        r = self.client.delete(self._likes_url(self.post.pk))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.data.get('deleted'))
        self.assertFalse(Like.objects.filter(user=self.user, post=self.post).exists())
        self.assertTrue(Like.objects.filter(user=self.other, post=self.post).exists())

    def test_delete_without_own_like_returns_404(self):
        self._auth(self.user)
        r = self.client.delete(self._likes_url(self.post.pk))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_like_missing_post_returns_404(self):
        self._auth(self.user)
        missing_id = Post.objects.order_by('-id').values_list('id', flat=True).first() or 0
        missing_id += 9999
        r = self.client.delete(self._likes_url(missing_id))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_post_detail_likes_count_tracks_like_and_unlike(self):
        detail_url = reverse('post-detail', kwargs={'pk': self.post.pk})
        self._clear_auth()
        r0 = self.client.get(detail_url)
        self.assertEqual(r0.status_code, status.HTTP_200_OK)
        self.assertEqual(r0.data['likes_count'], 0)

        self._auth(self.user)
        self.client.post(self._likes_url(self.post.pk))
        self._clear_auth()
        r1 = self.client.get(detail_url)
        self.assertEqual(r1.data['likes_count'], 1)

        self._auth(self.user)
        self.client.delete(self._likes_url(self.post.pk))
        self._clear_auth()
        r2 = self.client.get(detail_url)
        self.assertEqual(r2.data['likes_count'], 0)

    def test_comments_and_posts_crud_regression_with_likes(self):
        # Регрессия: комментарии и CRUD постов после сценария с лайками
        self._auth(self.user)
        self.client.post(self._likes_url(self.post.pk))
        c_url = reverse('post-comment-create', kwargs={'post_id': self.post.pk})
        c_resp = self.client.post(c_url, {'text': 'После лайка'}, format='json')
        self.assertEqual(c_resp.status_code, status.HTTP_201_CREATED)

        self._auth(self.other)
        self.assertEqual(
            self.client.patch(
                reverse('post-detail', kwargs={'pk': self.post.pk}),
                {'text': 'Чужая правка'},
                format='json',
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self._auth(self.user)
        patch_resp = self.client.patch(
            reverse('post-detail', kwargs={'pk': self.post.pk}),
            {'text': 'Автор правит'},
            format='json',
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)


class ApiRoutingStage10Tests(TestCase):
    """Маршрутизация API и токен (этап 10): префикс /api/, админка, эндпоинты постов/комментариев/лайков/токена."""

    def setUp(self):
        self.api = APIClient()
        self.django_client = Client()
        self.user = User.objects.create_user(
            username='route10_user',
            password='route10-secret',
        )
        self.post = Post.objects.create(
            author=self.user,
            text='Пост для маршрутов',
            image=_tiny_png(),
        )

    def test_root_resolves_api_posts_under_api_prefix(self):
        # Корневой urls.py подключает приложение под префиксом /api/
        match = resolve(f'/api/posts/{self.post.pk}/')
        self.assertEqual(match.url_name, 'post-detail')

    def test_admin_login_page_reachable(self):
        # Админка доступна (форма входа без сессии)
        r = self.django_client.get('/admin/login/')
        self.assertEqual(r.status_code, 200)

    def test_superuser_admin_index_returns_200(self):
        admin_user = User.objects.create_superuser(
            username='route10_admin',
            email='route10@example.com',
            password='admin-secret-10',
        )
        self.django_client.force_login(admin_user)
        r = self.django_client.get(reverse('admin:index'))
        self.assertEqual(r.status_code, 200)

    def test_get_api_posts_list_returns_200(self):
        r = self.api.get('/api/posts/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_get_api_post_detail_returns_200_for_existing_post(self):
        r = self.api.get(f'/api/posts/{self.post.pk}/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data.get('id'), self.post.pk)

    def test_post_api_comments_behaves_as_expected(self):
        token = Token.objects.create(user=self.user)
        self.api.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        r = self.api.post(
            f'/api/posts/{self.post.pk}/comments/',
            {'text': 'Маршрут комментария'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data.get('text'), 'Маршрут комментария')

    def test_post_and_delete_api_likes_behave_as_expected(self):
        token = Token.objects.create(user=self.user)
        self.api.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        url = f'/api/posts/{self.post.pk}/likes/'
        r_post = self.api.post(url)
        self.assertEqual(r_post.status_code, status.HTTP_201_CREATED)
        r_del = self.api.delete(url)
        self.assertEqual(r_del.status_code, status.HTTP_200_OK)
        self.assertFalse(Like.objects.filter(user=self.user, post=self.post).exists())

    def test_post_api_token_valid_credentials_returns_token(self):
        r = self.api.post(
            '/api/token/',
            {'username': 'route10_user', 'password': 'route10-secret'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn('token', r.data)
        self.assertTrue(r.data['token'])

    def test_post_api_token_invalid_credentials_returns_error(self):
        r = self.api.post(
            '/api/token/',
            {'username': 'route10_user', 'password': 'wrong-password'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class TokenAuthStage11Tests(TestCase):
    """Этап 11: выдача токена через /api/token/, создание пользователя и защита эндпоинтов."""

    def setUp(self):
        self.client = APIClient()
        self.password = 'stage11-secret-pass'
        self.user = User.objects.create_user(
            username='stage11_user',
            password=self.password,
        )

    def test_user_created_via_orm_exists_and_checks_password(self):
        # Пользователь создан через ORM; пароль проверяется стандартным хешем Django
        self.assertTrue(User.objects.filter(username='stage11_user').exists())
        u = User.objects.get(username='stage11_user')
        self.assertTrue(u.check_password(self.password))

    def test_superuser_created_via_orm_is_staff_and_superuser(self):
        # Путь суперпользователя только для проверки в тестах (без постоянных учёток в коде)
        su = User.objects.create_superuser(
            username='stage11_su',
            email='stage11_su@example.test',
            password='stage11-su-pass',
        )
        self.assertTrue(su.is_superuser)
        self.assertTrue(su.is_staff)

    def test_token_endpoint_valid_credentials_returns_200_and_token_field(self):
        # POST /api/token/ с верными данными — 200 и поле token (DRF authtoken)
        url = reverse('api-token')
        r = self.client.post(
            url,
            {'username': 'stage11_user', 'password': self.password},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn('token', r.data)
        self.assertTrue(r.data['token'])
        # Токен в БД привязан к этому пользователю
        token_obj = Token.objects.get(key=r.data['token'])
        self.assertEqual(token_obj.user_id, self.user.id)

    def test_token_endpoint_invalid_credentials_returns_400(self):
        url = reverse('api-token')
        r = self.client.post(
            url,
            {'username': 'stage11_user', 'password': 'wrong-password'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_create_without_token_returns_401(self):
        self.client.credentials()
        r = self.client.post(
            reverse('post-list'),
            {'text': 'Без токена', 'image': _tiny_png()},
            format='multipart',
        )
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_from_login_allows_post_and_author_is_authenticated_user(self):
        # Полный цикл: логин на /api/token/ → Authorization: Token … → создание поста
        login = self.client.post(
            reverse('api-token'),
            {'username': 'stage11_user', 'password': self.password},
            format='json',
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        token_key = login.data['token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token_key}')
        r = self.client.post(
            reverse('post-list'),
            {'text': 'Пост после логина', 'image': _tiny_png()},
            format='multipart',
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        created = Post.objects.get(text='Пост после логина')
        self.assertEqual(created.author_id, self.user.id)

    def test_token_from_login_allows_comment_and_like(self):
        # Тот же токен подходит для комментария и лайка
        post = Post.objects.create(
            author=self.user,
            text='Пост для комментария и лайка',
            image=_tiny_png(),
        )
        login = self.client.post(
            reverse('api-token'),
            {'username': 'stage11_user', 'password': self.password},
            format='json',
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {login.data["token"]}')

        c_url = reverse('post-comment-create', kwargs={'post_id': post.pk})
        c_resp = self.client.post(c_url, {'text': 'Из e2e токена'}, format='json')
        self.assertEqual(c_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Comment.objects.filter(post=post, author=self.user).count(), 1)

        l_url = reverse('post-like-create', kwargs={'post_id': post.pk})
        l_resp = self.client.post(l_url)
        self.assertIn(l_resp.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
        self.assertTrue(Like.objects.filter(user=self.user, post=post).exists())


class Stage12MediaAndValidationTests(TestCase):
    """Этап 12: ответы API с полем image и валидация без ответов 500."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='stage12_user', password='stage12-pw')
        self.post = Post.objects.create(
            author=self.user,
            text='Пост для комментария',
            image=_tiny_png(),
        )
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def test_image_present_as_string_in_create_list_detail_responses(self):
        # После multipart-создания image сериализуется строкой в ответе, списке и детали
        create_resp = self.client.post(
            reverse('post-list'),
            {'text': 'Пост с картинкой S12', 'image': _tiny_png()},
            format='multipart',
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        self.assertIn('image', create_resp.data)
        self.assertIsInstance(create_resp.data['image'], str)
        self.assertTrue(create_resp.data['image'].strip())

        post_id = create_resp.data['id']
        self.client.credentials()
        list_resp = self.client.get(reverse('post-list'))
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        row = next(item for item in list_resp.data if item['id'] == post_id)
        self.assertIsInstance(row.get('image'), str)
        self.assertTrue(str(row.get('image', '')).strip())

        detail_resp = self.client.get(reverse('post-detail', kwargs={'pk': post_id}))
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK)
        self.assertIsInstance(detail_resp.data.get('image'), str)
        self.assertTrue(str(detail_resp.data.get('image', '')).strip())

    def test_comment_missing_or_empty_text_returns_400_not_500(self):
        # Пустой или отсутствующий текст комментария — ошибка валидации DRF, не падение сервера
        url = reverse('post-comment-create', kwargs={'post_id': self.post.pk})
        r_empty = self.client.post(url, {'text': ''}, format='json')
        self.assertEqual(r_empty.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(r_empty.status_code >= 500)

        r_missing = self.client.post(url, {}, format='json')
        self.assertEqual(r_missing.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(r_missing.status_code >= 500)
