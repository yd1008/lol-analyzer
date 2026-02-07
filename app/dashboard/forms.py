import re
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, ValidationError, Regexp
from app.analysis.riot_api import VALID_REGIONS, REGION_DISPLAY


class RiotAccountForm(FlaskForm):
    summoner_name = StringField('Summoner Name', validators=[
        DataRequired(message='Summoner name is required.'),
        Length(max=64, message='Summoner name is too long.'),
    ])
    tagline = StringField('Tagline', validators=[
        DataRequired(message='Tagline is required (the part after # in your Riot ID).'),
        Length(max=16, message='Tagline is too long.'),
    ])
    region = SelectField('Region', choices=[
        (r, REGION_DISPLAY.get(r, r.upper())) for r in VALID_REGIONS
    ], validators=[DataRequired()])
    submit = SubmitField('Link Account')

    def validate_tagline(self, field):
        if field.data.startswith('#'):
            raise ValidationError('Do not include the # symbol. Just enter the tag itself (e.g. "NA1").')
        if not re.match(r'^[a-zA-Z0-9]+$', field.data):
            raise ValidationError('Tagline should only contain letters and numbers.')


class DiscordConfigForm(FlaskForm):
    channel_id = StringField('Channel ID', validators=[
        DataRequired(message='Channel ID is required.'),
        Length(max=64, message='Channel ID is too long.'),
        Regexp(r'^\d{17,20}$', message='Channel ID must be a 17-20 digit number. Right-click the channel in Discord to copy it.'),
    ])
    guild_id = StringField('Server ID (optional)', validators=[
        Optional(),
        Length(max=64),
        Regexp(r'^\d{17,20}$', message='Server ID must be a 17-20 digit number.'),
    ])
    submit = SubmitField('Save Discord Config')


class PreferencesForm(FlaskForm):
    check_interval = SelectField(
        'Check Interval (minutes)',
        choices=[('3', '3'), ('5', '5'), ('10', '10'), ('15', '15'), ('30', '30')],
        default='5'
    )
    weekly_summary_day = SelectField(
        'Weekly Summary Day',
        choices=[
            ('Monday', 'Monday'), ('Tuesday', 'Tuesday'), ('Wednesday', 'Wednesday'),
            ('Thursday', 'Thursday'), ('Friday', 'Friday'), ('Saturday', 'Saturday'),
            ('Sunday', 'Sunday')
        ],
        default='Monday'
    )
    weekly_summary_time = SelectField(
        'Weekly Summary Time',
        choices=[(f'{h:02d}:00', f'{h:02d}:00') for h in range(24)],
        default='09:00'
    )
    notifications_enabled = BooleanField('Enable Discord Notifications')
    submit = SubmitField('Save Preferences')
