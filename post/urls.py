from django.urls import path

from post.views import PostListApiView, PostCreateView, PostRetrieveUpdateDestroyAPIView,\
    PostCommentList, PostCommentCreateView, CommentListCreateApiView

urlpatterns = [
    path('list/', PostListApiView.as_view()),
    path('create/', PostCreateView.as_view()),
    path('<uuid:pk>/', PostRetrieveUpdateDestroyAPIView.as_view()),
    path('<uuid:pk>/comments/', PostCommentList.as_view()),
    path('<uuid:pk>/comments/create/', PostCommentCreateView.as_view()),
    path('comments/', CommentListCreateApiView.as_view()),
]