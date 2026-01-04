import os
import logging
from flask import Flask
from .db.ups import (  
    db,                     # SQLAlchemy database instance
    UPSError,              # Base class for UPS errors
    UPSConnectionError,    # Connection error
    UPSCommandError,       # Command error
    UPSDataError,          # Data error
    save_ups_data,         # Data saving
    get_ups_data,          # Current data reading
    get_supported_value,   # Utility for value access
    data_lock,            # Lock for DB synchronization
    ups_lock,             # Lock for UPS synchronization
    configure_ups         # UPS parameters configuration
)

from .routes import register_routes
from .api import register_api_routes
from .socket import socketio, init_socketio
from .mail import EmailNotifier
from .settings import DB_URI, LOG_FILE, LOG_LEVEL_DEBUG, LOG_LEVEL_INFO
from core.logger import system_logger as logger
from .scheduler import scheduler
from .db.initializer import init_database
from core.report import report_manager, api_report, routes_report
from core.options import api_options, routes_options
from core.ups_management import ups_management_bp
logger.info("🏁 Initializating init")

def create_app(config=None):
    # Configure logging first
    root_logger = logger  # Now the centralized system logger
    
    # Remove all existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    # Ensure log directory exists
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    
    # Set log level from settings.txt
    log_level = os.environ.get('LOG_LEVEL', 'INFO')
    
    # Use appropriate format based on level
    if log_level == 'DEBUG':
        log_format = logging.Formatter(LOG_LEVEL_DEBUG.split(',')[1].strip())
    else:
        log_format = logging.Formatter(LOG_LEVEL_INFO.split(',')[1].strip())
    
    # Configure root logger to handle all logs
    if os.environ.get('LOG_FILE_ENABLED', 'true').lower() == 'true':
        system_handler = logging.FileHandler(LOG_FILE)
        system_handler.setFormatter(log_format)
        root_logger.addHandler(system_handler)
    
    root_logger.setLevel(getattr(logging, log_level))
    
    # Console handler only in debug mode
    if os.environ.get('DEBUG_MODE', 'development') == 'development':
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_format)
        root_logger.addHandler(console_handler)
    
    # Create Flask app
    app = Flask(__name__)
    
    # Configure database
    app.config['SQLALCHEMY_DATABASE_URI'] = DB_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize database only
    db.init_app(app)
    
    # Initialize socketio but don't connect services yet
    socketio.init_app(app)
    
    # Set the CACHE_TIMEZONE from the global app module
    # This is required for the report manager to work correctly
    try:
        from app import CACHE_TIMEZONE
        app.CACHE_TIMEZONE = CACHE_TIMEZONE
        logger.info(f"✅ Set app.CACHE_TIMEZONE from global module: {CACHE_TIMEZONE.zone}")
    except (ImportError, AttributeError) as e:
        import pytz
        app.CACHE_TIMEZONE = pytz.timezone('UTC')
        logger.warning(f"⚠️ Failed to get CACHE_TIMEZONE from app module: {str(e)}. Using UTC instead.")
    
    # Don't initialize scheduler here - we'll do it later
    # in a controlled sequence after database initialization
    
    with app.app_context():
        # Create tables but don't initialize services yet
        db.create_all()
    
    # Register mail and report managers
    report_manager.init_app(app)
    
    # Register report routes
    app.register_blueprint(api_report)
    app.register_blueprint(routes_report)
    
    # Register options routes
    app.register_blueprint(api_options)
    app.register_blueprint(routes_options)

    # Register UPS management routes
    app.register_blueprint(ups_management_bp)

    return app