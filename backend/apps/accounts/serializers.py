from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from config.public_urls import media_url

from .models import Profile, UserPrivacySetting

User = get_user_model()


PASSWORD_ERROR_MESSAGES = {
    'password_too_short': 'رمز عبور باید حداقل ۸ کاراکتر باشد.',
    'password_too_common': 'این رمز عبور خیلی ساده و قابل حدس است.',
    'password_entirely_numeric': 'رمز عبور نباید فقط از عدد ساخته شود.',
    'password_too_similar': 'رمز عبور نباید شبیه ایمیل یا نام کاربری باشد.',
}


def validate_user_password(password, user=None):
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        messages = [
            PASSWORD_ERROR_MESSAGES.get(error.code, error.message)
            for error in exc.error_list
        ]
        raise serializers.ValidationError(messages) from exc


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    def validate_email(self, value):
        return value.strip().lower()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.strip().lower()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    def validate_password(self, value):
        validate_user_password(value)
        return value


class ProfileSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['avatar'] = media_url(instance.avatar) or None
        return data

    class Meta:
        model = Profile
        fields = ['avatar', 'bio', 'preferred_language', 'is_email_verified', 'created_at', 'updated_at']
        read_only_fields = ['is_email_verified', 'created_at', 'updated_at']


class PrivacySettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPrivacySetting
        exclude = ['id', 'user', 'created_at', 'updated_at']


class MeSerializer(serializers.Serializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    is_verified = serializers.BooleanField(source='user.is_verified', read_only=True)
    profile = ProfileSerializer(read_only=True)


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('این ایمیل قبلاً ثبت شده است.')
        return value

    def validate_username(self, value):
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError('نام کاربری باید حداقل ۳ کاراکتر باشد.')
        if any(character.isspace() for character in value):
            raise serializers.ValidationError('نام کاربری نباید فاصله داشته باشد.')
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('این نام کاربری قبلاً استفاده شده است.')
        return value

    def validate(self, attrs):
        candidate = User(email=attrs.get('email', ''), username=attrs.get('username', ''))
        try:
            validate_user_password(attrs['password'], user=candidate)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({'password': exc.detail}) from exc
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
        )
        Profile.objects.get_or_create(user=user)
        return user
