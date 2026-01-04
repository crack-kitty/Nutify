"""
UPS Utility Functions Module.
This module provides utility functions for UPS operations.
"""

import logging
import subprocess
import threading
import pytz
from datetime import datetime
from flask import current_app

from core.settings import UPSC_BIN
from core.logger import database_logger as logger
# Import nut_parser for configuration file access
from core.db.nut_parser import get_ups_connection_params, get_nut_configuration

# UPS Configuration class for individual UPS devices
class UPSSingleConfig:
    """Configuration for a single UPS device"""

    def __init__(self, ups_id=None, host=None, name=None, command=None, timeout=10,
                 is_primary=False, is_enabled=True, friendly_name=None):
        self.ups_id = ups_id
        self.host = host
        self.name = name
        self.command = command or UPSC_BIN
        self.timeout = timeout
        self.is_primary = is_primary
        self.is_enabled = is_enabled
        self.friendly_name = friendly_name or name
        self.initialized = bool(host and name and command)
        self.config_source = "database"

    def configure(self, host, name, command, timeout):
        """Configure the UPS connection parameters"""
        self.host = host
        self.name = name
        self.command = command
        self.timeout = timeout
        self.initialized = bool(host and name and command)
        logger.debug(f"🔌 UPS configuration updated: host={self.host}, name={self.name}, initialized={self.initialized}")
        return self.initialized

    def is_initialized(self):
        """Check if UPS configuration is initialized"""
        return self.initialized and bool(self.host and self.name and self.command)

    def __str__(self):
        return f"UPSSingleConfig(id={self.ups_id}, name={self.name}, host={self.host}, primary={self.is_primary}, enabled={self.is_enabled})"


# UPS Configuration Manager for multi-UPS support
class UPSConfigManager:
    """
    Manager for multiple UPS device configurations.
    Replaces the old singleton pattern to support multi-UPS monitoring.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(UPSConfigManager, cls).__new__(cls)
            cls._instance.devices = {}  # {ups_id: UPSSingleConfig}
            cls._instance.initialized = False
            cls._instance.config_files_checked = False
        return cls._instance

    def load_from_database(self):
        """
        Load all enabled UPS devices from the database.

        Returns:
            bool: True if at least one UPS was loaded successfully
        """
        try:
            from core.db.ups import db
            from sqlalchemy import text

            result = db.session.execute(text("""
                SELECT id, name, friendly_name, host, is_primary, is_enabled
                FROM ups_devices
                WHERE is_enabled = 1
                ORDER BY order_index, id
            """))

            self.devices = {}
            for row in result:
                ups_id, name, friendly_name, host, is_primary, is_enabled = row

                config = UPSSingleConfig(
                    ups_id=ups_id,
                    host=host or 'localhost',
                    name=name,
                    command=UPSC_BIN,
                    timeout=10,
                    is_primary=bool(is_primary),
                    is_enabled=bool(is_enabled),
                    friendly_name=friendly_name or name
                )

                self.devices[ups_id] = config
                logger.debug(f"📦 Loaded UPS device: {config}")

            if self.devices:
                self.initialized = True
                logger.info(f"✅ Loaded {len(self.devices)} UPS device(s) from database")
                return True
            else:
                logger.warning("⚠️ No enabled UPS devices found in database")
                return False

        except Exception as e:
            logger.error(f"❌ Error loading UPS devices from database: {str(e)}")
            return False

    def load_from_config_files(self):
        """
        Load UPS configuration from NUT configuration files (backward compatibility).
        Creates a single UPS entry from the config files.

        Returns:
            bool: True if configuration loaded successfully
        """
        try:
            from core.db.nut_parser import get_ups_connection_params

            self.config_files_checked = True
            params = get_ups_connection_params()

            logger.debug("🔍 Attempting to load config from NUT files")

            if params and 'host' in params and 'name' in params:
                # Create a single UPS config from NUT files (backward compatibility)
                config = UPSSingleConfig(
                    ups_id=0,  # Use 0 for file-based config
                    host=params['host'],
                    name=params['name'],
                    command=UPSC_BIN,
                    timeout=10,
                    is_primary=True,
                    is_enabled=True,
                    friendly_name=params.get('name')
                )
                config.config_source = "nut_files"

                self.devices = {0: config}
                self.initialized = True

                logger.info(f"✅ UPS configuration loaded from NUT config files: {config}")
                return True
            else:
                logger.warning("⚠️ No UPS configuration found in NUT config files")
                return False

        except Exception as e:
            logger.error(f"❌ Error loading UPS configuration from NUT config files: {str(e)}")
            return False

    def ensure_initialized(self):
        """
        Ensure the manager is initialized. Try database first, then config files.

        Returns:
            bool: True if initialized successfully
        """
        if self.initialized:
            return True

        # Try database first
        if self.load_from_database():
            return True

        # Fall back to config files for backward compatibility
        if not self.config_files_checked:
            if self.load_from_config_files():
                return True

        return False

    def get_all_enabled(self):
        """
        Get all enabled UPS devices.

        Returns:
            list: List of UPSSingleConfig objects
        """
        self.ensure_initialized()
        return [config for config in self.devices.values() if config.is_enabled]

    def get_primary(self):
        """
        Get the primary UPS device.

        Returns:
            UPSSingleConfig: Primary UPS or first enabled device, or None
        """
        self.ensure_initialized()

        # First try to find explicitly marked primary
        for config in self.devices.values():
            if config.is_primary and config.is_enabled:
                return config

        # Fall back to first enabled device
        enabled = self.get_all_enabled()
        return enabled[0] if enabled else None

    def get_by_id(self, ups_id):
        """
        Get UPS configuration by ID.

        Args:
            ups_id: UPS device ID

        Returns:
            UPSSingleConfig: UPS configuration or None
        """
        self.ensure_initialized()
        return self.devices.get(ups_id)

    def get_by_name(self, name):
        """
        Get UPS configuration by name.

        Args:
            name: UPS device name

        Returns:
            UPSSingleConfig: UPS configuration or None
        """
        self.ensure_initialized()
        for config in self.devices.values():
            if config.name == name:
                return config
        return None

    def reload(self):
        """Reload UPS configurations from database"""
        self.initialized = False
        self.config_files_checked = False
        return self.ensure_initialized()

    def __str__(self):
        return f"UPSConfigManager({len(self.devices)} device(s), initialized={self.initialized})"


# Global instance (singleton)
ups_config_manager = UPSConfigManager()


# Backward compatibility wrapper
# This class mimics the old UPSConfig singleton interface for backward compatibility
class UPSConfig:
    """
    Backward compatibility wrapper for the old UPSConfig singleton.
    Delegates to the primary UPS in UPSConfigManager.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(UPSConfig, cls).__new__(cls)
        return cls._instance

    @property
    def host(self):
        primary = ups_config_manager.get_primary()
        return primary.host if primary else None

    @property
    def name(self):
        primary = ups_config_manager.get_primary()
        return primary.name if primary else None

    @property
    def command(self):
        primary = ups_config_manager.get_primary()
        return primary.command if primary else None

    @property
    def timeout(self):
        primary = ups_config_manager.get_primary()
        return primary.timeout if primary else None

    @property
    def initialized(self):
        return ups_config_manager.initialized

    @property
    def config_source(self):
        primary = ups_config_manager.get_primary()
        return primary.config_source if primary else "uninitialized"

    def configure(self, host, name, command, timeout):
        """Configure the primary UPS connection parameters (backward compatibility)"""
        primary = ups_config_manager.get_primary()
        if primary:
            return primary.configure(host, name, command, timeout)
        else:
            # Create a new single UPS config
            config = UPSSingleConfig(
                ups_id=0,
                host=host,
                name=name,
                command=command,
                timeout=timeout,
                is_primary=True,
                is_enabled=True
            )
            ups_config_manager.devices[0] = config
            ups_config_manager.initialized = True
            return True

    def load_from_config_files(self):
        """Load UPS configuration from NUT configuration files"""
        return ups_config_manager.load_from_config_files()

    def is_initialized(self):
        """Check if UPS configuration is initialized"""
        return ups_config_manager.ensure_initialized()

    def __str__(self):
        primary = ups_config_manager.get_primary()
        if primary:
            return f"UPSConfig(primary={primary})"
        return "UPSConfig(no devices)"

# Global instance for backward compatibility
ups_config = UPSConfig()

# Locks for synchronization
ups_lock = threading.Lock()
data_lock = threading.Lock()

class DotDict:
    """
    Utility class to access dictionaries as objects
    Example: instead of dict['key'] allows dict.key
    
    This implementation supports both attribute access (obj.key)
    and dictionary-style item assignment (obj['key'] = value)
    """
    def __init__(self, dictionary):
        self._data = {}
        for key, value in dictionary.items():
            setattr(self, key, value)
            self._data[key] = value
    
    def __getitem__(self, key):
        return self._data[key]
    
    def __setitem__(self, key, value):
        setattr(self, key, value)
        self._data[key] = value
        
    def __contains__(self, key):
        return key in self._data

# Alias DotDict as UPSData for better semantics
UPSData = DotDict

def configure_ups(host, name, command, timeout, source="api_call"):
    """
    Configure the UPS connection parameters
    
    Args:
        host: Hostname or IP of the UPS
        name: Name of the UPS in the NUT system
        command: Command to use (e.g. 'upsc')
        timeout: Timeout in seconds for commands
        source: Source of the configuration (nut_files, database, api_call, etc.)
    """
    # Debug logs to verify parameter values
    logger.debug(f"🔌 Setting UPS configuration: host={host}, name={name}, command={command}, timeout={timeout}, source={source}")
    
    # Set the source in the singleton class
    ups_config.config_source = source
    
    # Configure the singleton instance
    success = ups_config.configure(host, name, command, timeout)
    
    # Skip database update - this is now disabled as requested
    logger.info(f"⏩ Skipping UPS configuration save to database, using configuration files instead: host={host}, name={name}")
    
    # Verify the configuration was set properly
    logger.debug(f"🔌 UPS configuration after setting: {ups_config}")
    logger.info(f"UPS configuration updated: host={host}, name={name}, source={source}")
    return success

def utc_to_local(utc_dt):
    """
    Convert UTC datetime to local timezone.
    
    Args:
        utc_dt: UTC datetime object
        
    Returns:
        datetime: Local timezone datetime object
    """
    if utc_dt is None:
        return None
        
    # Ensure datetime has UTC timezone
    if utc_dt.tzinfo is None:
        utc_dt = pytz.UTC.localize(utc_dt)
    elif utc_dt.tzinfo != pytz.UTC:
        utc_dt = utc_dt.astimezone(pytz.UTC)
        
    # Convert to local timezone using CACHE_TIMEZONE
    return utc_dt.astimezone(current_app.CACHE_TIMEZONE)

def local_to_utc(local_dt):
    """
    Convert local timezone datetime to UTC.
    
    Args:
        local_dt: Local timezone datetime object
        
    Returns:
        datetime: UTC datetime object
    """
    if local_dt is None:
        return None
        
    # If datetime has no timezone, assume it's in local timezone from CACHE_TIMEZONE
    if local_dt.tzinfo is None:
        local_dt = current_app.CACHE_TIMEZONE.localize(local_dt)
        
    # Convert to UTC
    return local_dt.astimezone(pytz.UTC)

def get_supported_value(data, field, default='N/A'):
    """
    Get a value from the UPS data with missing value handling
    
    Args:
        data: Object containing the UPS data
        field: Name of the field to retrieve
        default: Default value if the field doesn't exist
    
    Returns:
        The value of the field or the default value
    """
    try:
        value = getattr(data, field, None)
        if value is not None and value != '':
            return value
        return default
    except AttributeError:
        return default

def calculate_realpower(data):
    """
    Calculate ups_realpower (real power) using the direct formula:
    Power = realpower_nominal * (ups.load/100)
    
    Priority for nominal power:
    1. First use the value directly from UPS (ups.realpower.nominal/ups_realpower_nominal)
    2. If not available from UPS, try from database
    3. Only use default value (1000W) as last resort
    
    Cases handled:
    1. Key doesn't exist (ups.realpower or ups_realpower) -> Calculate value
    2. Key exists but value is 0 -> Calculate value
    3. Key exists with non-zero value -> Keep existing value
    
    Args:
        data: Dictionary containing UPS data
        
    Returns:
        Updated data dictionary with calculated realpower
    """
    try:
        # Check both possible key formats (with dot or underscore)
        dot_key = 'ups.realpower'
        underscore_key = 'ups_realpower'
        
        # Get current value (if exists)
        current_value = None
        if dot_key in data:
            current_value = data[dot_key]
        elif underscore_key in data:
            current_value = data[underscore_key]
        
        # Calculate only if value doesn't exist or is 0
        if current_value is None or float(current_value) == 0:
            # Get load value, checking both formats
            load_value = None
            if 'ups.load' in data:
                load_value = data['ups.load']
            elif 'ups_load' in data:
                load_value = data['ups_load']
            
            load_percent = float(load_value if load_value is not None else 0)
            
            # Get nominal power with priority:
            # 1. Directly from UPS data
            # 2. From database
            # 3. Default value as last resort
            nominal_value = None
            
            # First check UPS data - highest priority
            if 'ups.realpower.nominal' in data:
                nominal_value = data['ups.realpower.nominal']
                logger.debug(f"⚡ Using nominal power from UPS data (ups.realpower.nominal): {nominal_value}W")
            elif 'ups_realpower_nominal' in data:
                nominal_value = data['ups_realpower_nominal']
                logger.debug(f"⚡ Using nominal power from UPS data (ups_realpower_nominal): {nominal_value}W")
            
            # If not found in UPS data, try database
            if nominal_value is None:
                try:
                    # Try to get from settings using the getter function
                    from core.settings import get_ups_realpower_nominal
                    db_value = get_ups_realpower_nominal()
                    if db_value is not None:
                        nominal_value = db_value
                        logger.debug(f"⚡ Using nominal power from database: {nominal_value}W")
                except (ImportError, AttributeError) as e:
                    logger.warning(f"⚠️ Could not get UPS nominal power from database: {str(e)}")
            
            # If still no value, use default as last resort
            if nominal_value is None:
                nominal_value = 1000  # Default to 1000W
                logger.warning(f"⚠️ No nominal power found in UPS data or database. Using default: {nominal_value}W")
            
            # Calculate real power if we have valid values
            if load_percent > 0 and float(nominal_value) > 0:
                nominal_power = float(nominal_value)
                realpower = (nominal_power * load_percent) / 100
                
                # Update both key versions for compatibility
                data[dot_key] = str(round(realpower, 2))
                data[underscore_key] = str(round(realpower, 2))
                
                logger.debug(f"Calculated realpower: {realpower:.2f}W (nominal={nominal_power}W, load={load_percent}%)")
            else:
                logger.warning(f"Cannot calculate realpower: load={load_percent}%, nominal={nominal_value}W")
    except Exception as e:
        logger.error(f"Error calculating realpower: {str(e)}", exc_info=True)
    
    return data 