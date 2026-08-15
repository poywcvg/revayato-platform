from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from config.public_urls import media_url
from users.username_policy import validate_username_policy

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
    login = serializers.CharField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    def validate_login(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('ایمیل یا نام کاربری را وارد کن.')
        return value


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
    is_staff = serializers.BooleanField(source='user.is_staff', read_only=True)
    is_superuser = serializers.BooleanField(source='user.is_superuser', read_only=True)
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
        try:
            value = validate_username_policy(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        if User.all_objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError(
                f'نام کاربری «{value}» قبلاً گرفته شده است. یک نام کاربری دیگر انتخاب کن.',
            )
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
