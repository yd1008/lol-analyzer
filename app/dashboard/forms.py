import re
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, ValidationError, Regexp
from app.analysis.riot_api import VALID_REGIONS, REGION_DISPLAY


class RiotAccountForm(FlaskForm):
    summoner_name = StringField('form.summoner_name', validators=[
        DataRequired(message='validation.summoner_required'),
        Length(max=64, message='validation.summoner_too_long'),
    ])
    tagline = StringField('form.tagline', validators=[
        DataRequired(message='validation.tagline_required'),
        Length(max=16, message='validation.tagline_too_long'),
    ])
    region = SelectField('form.region', choices=[
        (r, REGION_DISPLAY.get(r, r.upper())) for r in VALID_REGIONS
    ], validators=[DataRequired()])
    submit = SubmitField('form.link_account')

    def validate_tagline(self, field):
        if field.data.startswith('#'):
            raise ValidationError('validation.tagline_no_hash')
        if not re.match(r'^[a-zA-Z0-9]+$', field.data):
            raise ValidationError('validation.tagline_alnum')


class DiscordConfigForm(FlaskForm):
    channel_id = StringField('form.channel_id', validators=[
        DataRequired(message='validation.channel_required'),
        Length(max=64, message='validation.channel_too_long'),
        Regexp(r'^\d{17,20}$', message='validation.channel_format'),
    ])
    guild_id = StringField('form.server_id_optional', validators=[
        Optional(),
        Length(max=64, message='validation.channel_too_long'),
        Regexp(r'^\d{17,20}$', message='validation.guild_format'),
    ])
    submit = SubmitField('form.save_discord')


class PreferencesForm(FlaskForm):
    check_interval = SelectField(
        'form.check_interval',
        choices=[('3', '3'), ('5', '5'), ('10', '10'), ('15', '15'), ('30', '30')],
        default='5'
    )
    weekly_summary_day = SelectField(
        'form.weekly_summary_day',
        choices=[
            ('Monday', 'Monday'), ('Tuesday', 'Tuesday'), ('Wednesday', 'Wednesday'),
            ('Thursday', 'Thursday'), ('Friday', 'Friday'), ('Saturday', 'Saturday'),
            ('Sunday', 'Sunday')
        ],
        default='Monday'
    )
    weekly_summary_time = SelectField(
        'form.weekly_summary_time',
        choices=[(f'{h:02d}:00', f'{h:02d}:00') for h in range(24)],
        default='09:00'
    )
    notifications_enabled = BooleanField('form.enable_discord_notifications')
    submit = SubmitField('form.save_preferences')
