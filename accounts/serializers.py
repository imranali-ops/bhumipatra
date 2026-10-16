from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


class RegisterSerializer(serializers.Serializer):
    """Public sign-up. The role is NEVER read from the request: everyone who
    registers is a citizen. Officers are created by an administrator."""
    username = serializers.RegexField(r"^[A-Za-z0-9_.-]{4,30}$", max_length=30)
    email = serializers.EmailField(required=False, allow_blank=True, max_length=254)
    password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("এই ইউজারনেম ব্যবহার করা হয়েছে।")
        return value

    def validate(self, attrs):
        candidate = User(username=attrs["username"], email=attrs.get("email", ""))
        validate_password(attrs["password"], user=candidate)
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
        )


class MeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("username", "role")
        read_only_fields = fields
