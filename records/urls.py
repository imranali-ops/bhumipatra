from django.urls import path

from . import api

urlpatterns = [
    path("parcels/search/", api.ParcelSearchView.as_view(), name="parcel-search"),
    path("parcels/<uuid:pk>/", api.ParcelDetailView.as_view(), name="parcel-detail"),
    path("parcels/<uuid:pk>/qr.svg", api.ParcelQrView.as_view(), name="parcel-qr"),
    path("verify/<uuid:pk>/<str:head_prefix>/", api.PublicVerifyView.as_view(), name="public-verify"),
]
