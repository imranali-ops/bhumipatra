from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView

from audit.services import log_event

from . import lockout

from .serializers import MeSerializer, RegisterSerializer


def client_ip(request) -> str:
    """Client address. X-Forwarded-For is used only when TRUSTED_PROXY_COUNT > 0
    (we sit behind our own Next.js server), and then only the entry added by
    that trusted proxy, never what the client wrote."""
    count = settings.TRUSTED_PROXY_COUNT
    if count > 0:
        parts = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
        if parts:
            return parts[-min(count, len(parts))][:45]
    return request.META.get("REMOTE_ADDR", "")[:45]


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        log_event(actor=user, action="register", target_type="user",
                  target_id=user.pk, ip=client_ip(request))
        return Response({"username": user.username, "role": user.role},
                        status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        raw = request.data.get("username") if hasattr(request.data, "get") else ""
        username = str(raw or "")[:150]
        if username and lockout.is_locked(username):
            # same answer for every username, so this reveals nothing about accounts
            log_event(actor=None, action="login_failed", ip=client_ip(request),
                      metadata={"locked": True})
            return Response({"detail": "locked"}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except AuthenticationFailed:
            if username:
                lockout.record_failure(username)
            # Do not record the attempted username: people often type a
            # password into that field.
            log_event(actor=None, action="login_failed", ip=client_ip(request))
            raise
        except TokenError as exc:
            raise InvalidToken(exc.args[0])
        lockout.reset(username)
        log_event(actor=serializer.user, action="login_success", ip=client_ip(request))
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class RefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "refresh"


class LogoutView(TokenBlacklistView):
    """POST {"refresh": "..."} to invalidate a refresh token."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "refresh"


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(MeSerializer(request.user).data)
