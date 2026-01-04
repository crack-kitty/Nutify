"""
ORM Models Package.
This package contains individual ORM model definitions for each database table.
"""

from core.db.orm.orm_ups_devices import UPSDevice, init_model as init_ups_device_model
from core.db.orm.orm_ups_events import UPSEvent, init_model as init_ups_event_model
from core.db.orm.orm_ups_opt_variable_config import VariableConfig, init_model as init_variable_config_model
from core.db.orm.orm_ups_variables_upscmd import UPSCommand, init_model as init_ups_command_model
from core.db.orm.orm_ups_variables_upsrw import UPSVariable, init_model as init_ups_variable_model
from core.db.orm.orm_ups_opt_mail_config import MailConfig, init_model as init_mail_config_model
from core.db.orm.orm_ups_opt_ntfy import NtfyConfig, init_model as init_ntfy_config_model
from core.db.orm.orm_ups_opt_webhook import WebhookConfig, init_model as init_webhook_config_model
from core.db.orm.orm_ups_opt_notification import NotificationSettings, init_model as init_notification_settings_model
from core.db.orm.orm_ups_report_schedules import ReportSchedule, init_model as init_report_schedule_model
from core.db.orm.orm_ups_initial_setup import InitialSetup, init_model as init_initial_setup_model
from core.db.orm.orm_ups_login import LoginAuth, init_model as init_login_model


# Dictionary to store initialized models
_models = {}

def init_models(db_instance, timezone_getter=None):
    """
    Initialize all ORM models in this package.
    
    Args:
        db_instance: SQLAlchemy database instance
        timezone_getter: DEPRECATED, no longer used - direct CACHE_TIMEZONE is used instead
        
    Returns:
        dict: Dictionary of initialized model classes
    """
    global _models
    
    # Create the base class for all models
    class Base(db_instance.Model):
        """Base model with shared methods"""
        __abstract__ = True
        __table_args__ = {'extend_existing': True}
    
    # Import logger for database operations
    from core.logger import database_logger
    
    # Initialize InitialSetup model first as others may depend on it
    _models['InitialSetup'] = init_initial_setup_model(
        Base,
        database_logger
    )
    
    # Load secret key from Flask config for password encryption
    from flask import current_app
    secret_key = current_app.config.get('SECRET_KEY')
    if secret_key:
        secret_key = secret_key.encode()
        database_logger.info("🔑 Using secret key from environment variable for password encryption")
    else:
        database_logger.warning("⚠️ SECRET_KEY not set in Flask config; password encryption disabled")
        secret_key = None
    
    # Initialize UPSEvent model
    _models['UPSEvent'] = init_ups_event_model(Base)
    
    # Initialize VariableConfig model
    _models['VariableConfig'] = init_variable_config_model(Base)
    
    # Initialize UPSCommand model
    _models['UPSCommand'] = init_ups_command_model(Base)
    
    # Initialize UPSVariable model
    _models['UPSVariable'] = init_ups_variable_model(Base)
    
    # Initialize MailConfig model with secret key for password encryption
    _models['MailConfig'] = init_mail_config_model(
        Base, 
        secret_key, 
        database_logger
    )
    
    # Initialize NtfyConfig model
    _models['NtfyConfig'] = init_ntfy_config_model(
        Base,
        database_logger
    )
    
    # Initialize WebhookConfig model
    _models['WebhookConfig'] = init_webhook_config_model(
        Base,
        database_logger
    )
    
    # Initialize NotificationSettings model
    _models['NotificationSettings'] = init_notification_settings_model(
        Base,
        db_instance,
        database_logger
    )
    
    # Initialize ReportSchedule model
    _models['ReportSchedule'] = init_report_schedule_model(
        Base,
        database_logger
    )
    
    # Initialize LoginAuth model
    _models['LoginAuth'] = init_login_model(
        Base,
        database_logger
    )

    # Initialize UPSDevice model (multi-UPS support)
    _models['UPSDevice'] = init_ups_device_model(
        Base,
        database_logger
    )

    # NUTConfig model has been removed as it's no longer used
    # Configuration is now managed through NUT configuration files
    
    # UPSStaticData and UPSDynamicData models are created dynamically by db_module.py
    # and not part of the standard ORM package
    
    # Return a dictionary of all initialized models
    return _models

# Export public symbols
__all__ = [
    'init_models',
    'UPSDevice',
    'UPSEvent',
    'VariableConfig',
    'UPSCommand',
    'UPSVariable',
    'MailConfig',
    'NtfyConfig',
    'WebhookConfig',
    'NotificationSettings',
    'ReportSchedule',
    'InitialSetup',
    'LoginAuth'
    # Removed NUTConfig as it's no longer used
    # Removed UPSStaticData and UPSDynamicData from exports
]
