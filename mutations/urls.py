from django.urls import path

from . import views

urlpatterns = [
    path("mutations/", views.SubmitView.as_view(), name="mutation-submit"),
    path("mutations/mine/", views.MineView.as_view(), name="mutation-mine"),
    path("mutations/queue/", views.QueueView.as_view(), name="mutation-queue"),
    path("mutations/<uuid:pk>/", views.DetailView.as_view(), name="mutation-detail"),
    path("mutations/<uuid:pk>/action/", views.ActionView.as_view(), name="mutation-action"),
    path("mutations/<uuid:pk>/documents/", views.DocumentUploadView.as_view(), name="document-upload"),
    path("mutations/<uuid:pk>/documents/<int:doc_id>/", views.DocumentDownloadView.as_view(), name="document-download"),
    path("notifications/", views.NotificationListView.as_view(), name="notifications"),
    path("notifications/<int:pk>/read/", views.NotificationReadView.as_view(), name="notification-read"),
]
