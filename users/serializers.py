from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from django.contrib.messages import success
from django.core.validators import FileExtensionValidator
from django.shortcuts import get_object_or_404
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.views import TokenObtainPairView

from shared.utility import check_email_or_phone, send_email, send_phone_code, check_user_type
from .models import User, UserConfirmation, VIA_EMAIL, VIA_PHONE, NEW, CODE_VERIFIED, DONE, PHOTO_STEP
from rest_framework import serializers, exceptions
from django.db.models import Q
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound


class SignUpSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    def __init__(self, *args, **kwargs):
        super(SignUpSerializer, self).__init__(*args, **kwargs)
        self.fields['email_phone_number'] = serializers.CharField(required=False) # modelsda yo'q bo'lgan 1ta field qo'shdik


    class Meta:
        model = User
        fields = ('id', 'email', 'phone_number', 'auth_type', 'auth_status')
        # fields = ('id', 'auth_type', 'auth_status')
        extra_kwargs = {
            'auth_type': {'write_only': True, 'required': False},
            'auth_status': {'write_only': True, 'required': False},
        }

    def create(self, validated_data):
        user = super(SignUpSerializer, self).create(validated_data)
        print(user)
        # user -> email -> email jo'natish kerak
        # user -> phone -> telefoniga codeni jo'natish kerak
        if user.auth_type == VIA_EMAIL:
            code = user.create_verify_code(VIA_EMAIL)
            print(code)
            send_email(user.email, code)
        elif user.auth_type == VIA_PHONE:
            code = user.create_verify_code(VIA_PHONE)
            print(code)
            send_email(user.email, code)
            # send_phone_code(user.phone_number, code)
        user.save()
        return user

    def validate(self, data):
        super(SignUpSerializer, self).validate(data)
        data = self.auth_validate(data)
        return data


    @staticmethod
    def auth_validate(data):
        user_input = str(data.get('email_phone_number')).lower()
        input_type = check_email_or_phone(user_input)  # tekshirish email or phone
        if input_type =="email":
            data = {
                "email": user_input,
                'auth_type': VIA_EMAIL,
            }
        elif input_type == "phone":
            data = {
                "phone_number": user_input,
                'auth_type': VIA_PHONE,
            }
        else:
            data = {
                "success": False,
                "message": "you must send email or phone number",
            }
            raise ValidationError(data)

        return data

    def validate_email_phone_number(self, value):
        value = value.lower()
        if value and User.objects.filter(email=value).exists():
            data = {
                "success": False,
                "message": "Bu email Allaqachon ma'lumotlar bazasida bor",
            }
            raise ValidationError(data)
        elif value and User.objects.filter(phone_number=value).exists():
            data = {
                "success": False,
                "message": "Bu telefonraqami Allaqachon ma'lumotlar bazasida bor",
            }
            raise ValidationError(data)
        # to do
        return value

    def to_representation(self, instance):
        print("to-rep", instance)
        data = super(SignUpSerializer, self).to_representation(instance)
        data.update(instance.token())



class ChangeUserInformation(serializers.Serializer):
    first_name = serializers.CharField(write_only=True, required=False)
    last_name = serializers.CharField(write_only=True, required=False)
    username = serializers.CharField(write_only=True, required=False)
    password = serializers.CharField(write_only=True, required=False)
    confirm_password = serializers.CharField(write_only=True, required=False)

    def validate(self, data):
        password = data.get('password', None)
        confirm_password = data.get('confirm_password', None)
        if password != confirm_password:
            raise ValidationError(
                {
                    "message": "passwords don't match",
                }
            )
        if password:
            validate_password(password)
            validate_password(confirm_password)
        return data

    def validate_username(self, username):
        if len(username) < 5 or len(username) > 30:
            raise ValidationError({
                "message": "username must be between 5 and 30 characters",
            })
        if username.isdigit():
            raise ValidationError({
                "message": "username can't be a number",
            })
        return username


    def validate_first_name(self, first_name):
        if len(first_name) < 5 or len(first_name) > 30:
            raise ValidationError({
                "message": "first_name must be between 5 and 30 characters",
            })
        if first_name.isdigit():
            raise ValidationError({
                "message": "first_name can't be a number",
            })
        return first_name

    def validate_last_name(self, last_name):
        if len(last_name) < 5 or len(last_name) > 30:
            raise ValidationError({
                "message": "last_name must be between 5 and 30 characters",
            })
        if last_name.isdigit():
            raise ValidationError({
                "message": "last_name can't be a number",
            })
        return last_name

    def update(self, instance, validated_data):

        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.username = validated_data.get('username', instance.username)
        instance.password = validated_data.get('password', instance.password)

        if validated_data.get("password"):
            instance.set_password(validated_data.get('password'))
        if instance.auth_status == CODE_VERIFIED:
            instance.auth_status = DONE
        instance.save()
        return instance


class ChangeUserPhotoSerializer(serializers.Serializer):
    photo = serializers.ImageField(validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'heic', 'heif'])])

    def update(self, instance, validated_data):
        photo = validated_data.get('photo')
        if photo:
            instance.photo = photo
            instance.auth_status = PHOTO_STEP
            instance.save()
        return instance



################### LOGIN  ###################

class LoginSerializer(TokenObtainPairSerializer):

    def __init__(self, *args, **kwargs):
        super(LoginSerializer, self).__init__(*args, **kwargs)
        self.fields['userinput'] = serializers.CharField(required=True)
        self.fields['username'] = serializers.CharField(required=False, read_only=True)

    def aut_validate(self, data):
        user_input = data.get('userinput')
        if check_user_type(user_input) == 'username':
            username = user_input
        elif check_user_type(user_input) == 'email':
            user = self.get_user(email__iexact=user_input)
            username = user.username
        elif check_user_type(user_input) == 'phone':
            user = self.get_user(phone_number=user_input)
            username = user.username
        else:
            data = {
                "success": True,
                "message": "Siz email, username yoki telefon raqami kiritishingiz kerka",
            }
            raise ValidationError(data)
        authentication_kwargs = {
            self.username_field: username,
            "password": data['password'],
        }

        current_user = User.objects.filter(username__iexact=username).first()
        if current_user is not None and current_user.auth_status in [NEW, CODE_VERIFIED]:
            raise ValidationError({
                "success": False,
                "message": "Siz ro'yxatdan to'liq o'tmagansiz"
            })

        user = authenticate(authentication_kwargs)
        if user is not None:
            self.user = user
        else:
            raise ValidationError({
                "success": False,
                "message": "sorry, login or password ypu intered is in correcct, please check and try again",
            })

    def validate(self, data):
        self.aut_validate(data)
        if self.user.auth_status not in [DONE, PHOTO_STEP]:
            raise PermissionDenied("Login qila olmaysiz ruxsatingiz yo'q")
        data = self.user.token()
        data['auth_status'] = self.user.auth_status
        data['full_name'] = self.user.full_name


    def get_user(self, **kwargs):
        users = User.objects.filter(**kwargs)
        if not users.exists():
            raise ValidationError({
                "message": "User not found",
            })
        return users.first()


class AccessTokenToken:
    pass


class LoginRefreshSerializer(TokenRefreshSerializer):

    def validate(self, attrs):
        data = super().validate(attrs)
        access_token_instance = AccessToken(data['access'])
        user_id = access_token_instance['user_id']
        user = get_object_or_404(User, id=user_id)
        update_last_login(None, user)
        return data



class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ForgotPasswordSerializer(serializers.Serializer):
    email_or_phone = serializers.CharField(write_only=True, required=True)

    def validate(self, attrs):
        email_or_phone = attrs.get('email_or_phone', None)
        if email_or_phone is None:
             raise ValidationError({
                 "success": False,
                 "message": "Please enter a valid email address or phone number"
             })
        user = User.objects.filter(Q(email__iexact=email_or_phone) | Q(phone_number__iexact=email_or_phone))
        if not user.exists():
            raise NotFound("User not found")
        attrs['user'] = user.first()
        return attrs





class ResetPasswordSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    password = serializers.CharField(max_length=8, write_only=True, required=True)
    confirm_password = serializers.CharField(max_length=8, write_only=True, required=True)

    class Meta:
        model = User
        fields = ('id', 'password', 'confirm_password')

    def validate(self, data):
        password = data.get('password', None)
        confirm_password = data.get('confirm_password', None)
        if password != confirm_password:
            raise ValidationError({
                "success": False,
                "message": "Passwords don't match",
            })
        if password:
            validate_password(password)
        return data

    def update(self, instance, validated_data):
        password = validated_data.pop('password')
        instance.set_password(password)
        return super(ResetPasswordSerializer, self).update(instance, validated_data)