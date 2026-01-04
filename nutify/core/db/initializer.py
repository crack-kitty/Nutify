"""
Database initialization module.
This module provides functions to initialize the database properly
using SQLAlchemy ORM.
"""

import logging
import os
from sqlalchemy import text, inspect
import time
from flask import current_app

from .integrity import check_database_integrity
from core.logger import system_logger as logger
from core.db.model_classes import init_model_classes, register_models_for_global_access

def get_app_timezone():
    """
    Returns the application's CACHE_TIMEZONE.
    This is used for database models that need timezone information.
    Database always uses UTC, while display uses CACHE_TIMEZONE.
    
    Returns:
        timezone: The timezone object from current_app.CACHE_TIMEZONE
    """
    # For database operations, always use UTC
    import pytz
    return lambda: pytz.UTC

def init_database(app, db):
    """
    Initialize the database with all tables using ORM.
    
    Args:
        app: Flask application instance
        db: SQLAlchemy database instance
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Initialize the models
        from .models import init_models
        
        # Clear separator for major initialization steps
        logger.info("=" * 50)
        logger.info("📚 DATABASE INITIALIZATION SEQUENCE START")
        logger.info("=" * 50)
        
        # Step 1: Initialize the UPS static data model and table
        logger.info("📦 Step 1: Creating and initializing UPS static data model...")
        from core.db.ups.models import create_static_model
        static_model = create_static_model(db)
        
        # Create the static data table
        inspector = inspect(db.engine)
        if 'ups_static_data' not in inspector.get_table_names():
            static_model.__table__.create(db.engine)
            logger.info("✅ UPS static data table created")
        else:
            logger.info("✅ UPS static data table already exists")
        
        # Step 2: Initialize the UPS dynamic data model and table
        logger.info("📦 Step 2: Creating and initializing UPS dynamic data model...")
        from core.db.ups.models import create_dynamic_model
        dynamic_model = create_dynamic_model(db)
        
        # Create the dynamic data table
        if 'ups_dynamic_data' not in inspector.get_table_names():
            dynamic_model.__table__.create(db.engine)
            logger.info("✅ UPS dynamic data table created")
        else:
            logger.info("✅ UPS dynamic data table already exists")
        
        logger.info("✅ UPS data models initialized successfully")
        
        # Step 3: Initialize static data if needed
        logger.info("🔄 Step 3: Initializing UPS static data...")
        from core.db.ups.models import initialize_static_data_if_needed
        initialize_static_data_if_needed(db)
        logger.info("✅ UPS static data initialized")
        
        # Step 4: Initialize dynamic data if needed
        logger.info("🔄 Step 4: Initializing UPS dynamic data...")
        from core.db.ups.models import insert_initial_dynamic_data
        insert_initial_dynamic_data(db)
        logger.info("✅ UPS dynamic data initialized")
        
        # Step 5: Initialize the ORM models for other tables
        logger.info("📦 Step 5: Initializing ORM models for other tables...")
        models_dict = init_models(db, get_app_timezone())
        
        # Explicitly attach models to db.ModelClasses namespace for global access
        if not hasattr(db, 'ModelClasses'):
            # Use the ModelClasses module to create a proper ModelClasses instance
            model_classes = init_model_classes(db, get_app_timezone())
            db.ModelClasses = model_classes
            logger.info("✅ Models attached to db.ModelClasses namespace")
            
        logger.info("✅ ORM models initialized successfully")
        
        # Step 6: Create all tables from the ORM models
        # NOTE: This will not affect ups_static_data and ups_dynamic_data tables
        # as they were already created in steps 1-2
        logger.info("🏗️ Step 6: Creating remaining tables...")
        db.create_all()
        logger.info("✅ All tables created successfully")

        # Step 6.5: Run multi-UPS migration if needed
        logger.info("🔄 Step 6.5: Checking for multi-UPS migration...")
        from core.db.migrations import check_migration_needed, run_multi_ups_migration
        if check_migration_needed(db):
            logger.info("🚀 Running multi-UPS migration...")
            if run_multi_ups_migration(db, app):
                logger.info("✅ Multi-UPS migration completed successfully")
            else:
                logger.warning("⚠️ Multi-UPS migration encountered issues")
        else:
            logger.info("✅ Multi-UPS schema already up to date")

        # Step 7: Register models in UPS module to ensure they're available globally
        logger.info("🔗 Step 7: Registering models globally...")
        from core.db.ups import register_models_from_modelclasses
        register_models_from_modelclasses(db.ModelClasses)
        logger.info("✅ Models registered globally")
        
        # Step 8: Check database integrity
        # NOTE: ups_static_data and ups_dynamic_data are protected and not modified by this process
        logger.info("=" * 50)
        logger.info("🔍 Step 8: CHECKING DATABASE INTEGRITY")
        logger.info("=" * 50)
        
        integrity_results = check_database_integrity(db)
        logger.info("✅ Database integrity check completed")
        
        # Step 9: Initialize default configurations and settings
        logger.info("🔧 Step 9: Initializing default configurations...")
        
        # Initialize variable configuration
        try:
            # Ensure ModelClasses is attached to db
            if hasattr(db, 'ModelClasses'):
                # Initialize VariableConfig defaults if available
                if hasattr(db.ModelClasses, 'VariableConfig'):
                    try:
                        db.ModelClasses.VariableConfig.init_default_config()
                        logger.info("✅ Default variable configuration initialized")
                    except Exception as ve:
                        logger.warning(f"⚠️ Error initializing variable configuration: {str(ve)}")
                else:
                    logger.warning("⚠️ VariableConfig model not available, skipping default config initialization")
                
                # Initialize notification settings if available
                if hasattr(db.ModelClasses, 'NotificationSettings'):
                    try:
                        db.ModelClasses.NotificationSettings.init_notification_settings()
                        logger.info("✅ Default notification settings initialized")
                    except Exception as ne:
                        logger.warning(f"⚠️ Error initializing notification settings: {str(ne)}")
                else:
                    logger.warning("⚠️ NotificationSettings model not available, skipping notification settings initialization")
                
                # Update global settings from database
                if hasattr(db.ModelClasses, 'InitialSetup'):
                    try:
                        # Update server_name with value from database
                        from core.settings import get_server_name
                        server_name = get_server_name()
                        logger.info(f"✅ Global server_name updated to: {server_name}")
                    except Exception as se:
                        logger.warning(f"⚠️ Error updating global server_name: {str(se)}")
            else:
                logger.warning("⚠️ ModelClasses namespace not available on db, skipping default configuration initialization")
                
        except Exception as e:
            logger.warning(f"⚠️ Error initializing default configurations: {str(e)}")
        
        # Final success message
        logger.info("=" * 50)
        logger.info("✅ DATABASE INITIALIZATION COMPLETE")
        logger.info("=" * 50)
        
        return True
    
    except Exception as e:
        logger.error(f"❌ Database initialization error: {str(e)}")
        return False 