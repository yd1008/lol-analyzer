from flask_wtf import FlaskForm
from wtforms import BooleanField, StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError
from app.models import User


class LoginForm(FlaskForm):
    email = StringField(
        'form.email',
        validators=[DataRequired(message='validation.email_invalid'), Email(message='validation.email_invalid')],
    )
    password = PasswordField('form.password', validators=[DataRequired(message='validation.password_required')])
    remember = BooleanField('Remember me')
    submit = SubmitField('form.sign_in')


class RegisterForm(FlaskForm):
    email = StringField(
        'form.email',
        validators=[DataRequired(message='validation.email_invalid'), Email(message='validation.email_invalid')],
    )
    password = PasswordField(
        'form.password',
        validators=[DataRequired(message='validation.password_required'), Length(min=8, message='validation.password_min')],
    )
    confirm_password = PasswordField(
        'form.confirm_password',
        validators=[
            DataRequired(message='validation.confirm_password_required'),
            EqualTo('password', message='validation.password_match'),
        ],
    )
    submit = SubmitField('form.create_account')

    def validate_email(self, field):
        if User.query.filter_by(email=field.data.lower()).first():
            raise ValidationError('validation.email_exists')
