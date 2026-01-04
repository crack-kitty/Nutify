"""
ORM Model for UPS Devices

This module defines the SQLAlchemy ORM model for the ups_devices table,
which stores configuration for multiple UPS devices.
"""

from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime
from datetime import datetime
import pytz
import json

# These will be set during initialization
db = None
logger = None


class UPSDevice:
    """
    UPS Device configuration model.

    Stores configuration and metadata for individual UPS devices in a multi-UPS setup.
    """
    __tablename__ = 'ups_devices'

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # UPS identification
    name = Column(String(50), nullable=False, unique=True, index=True)
    friendly_name = Column(String(100))

    # Connection configuration
    driver = Column(String(50), nullable=False)
    port = Column(String(255), nullable=False)
    host = Column(String(255), nullable=False, default='localhost')
    description = Column(Text)

    # Status flags
    is_enabled = Column(Boolean, nullable=False, default=True, index=True)
    is_primary = Column(Boolean, nullable=False, default=False)

    # Connection type
    connection_type = Column(String(20))  # 'local_usb', 'local_serial', 'remote_ups', 'remote_nut', 'snmp'

    # USB-specific fields
    vendor_id = Column(String(10))
    product_id = Column(String(10))
    serial = Column(String(100))

    # SNMP-specific fields
    snmp_version = Column(String(10))
    snmp_community = Column(String(50))

    # Serial-specific fields
    baudrate = Column(Integer)

    # Additional driver options (stored as JSON string)
    driver_options = Column(Text)

    # Display and ordering
    order_index = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(pytz.UTC))
    updated_at = Column(DateTime(timezone=True),
                      default=lambda: datetime.now(pytz.UTC),
                      onupdate=lambda: datetime.now(pytz.UTC))
    last_seen_at = Column(DateTime(timezone=True))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if logger:
            logger.debug(f"🆕 Creating UPS Device: {self.name}")

    def __repr__(self):
        return f"<UPSDevice(id={self.id}, name='{self.name}', friendly_name='{self.friendly_name}', enabled={self.is_enabled})>"

    def to_dict(self):
        """Convert model to dictionary representation."""
        return {
            'id': self.id,
            'name': self.name,
            'friendly_name': self.friendly_name,
            'driver': self.driver,
            'port': self.port,
            'host': self.host,
            'description': self.description,
            'is_enabled': self.is_enabled,
            'is_primary': self.is_primary,
            'connection_type': self.connection_type,
            'vendor_id': self.vendor_id,
            'product_id': self.product_id,
            'serial': self.serial,
            'snmp_version': self.snmp_version,
            'snmp_community': self.snmp_community,
            'baudrate': self.baudrate,
            'driver_options': self.driver_options,
            'order_index': self.order_index,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_seen_at': self.last_seen_at.isoformat() if self.last_seen_at else None
        }

    @classmethod
    def get_all_enabled(cls):
        """Get all enabled UPS devices, ordered by order_index."""
        return cls.query.filter_by(is_enabled=True).order_by(cls.order_index).all()

    @classmethod
    def get_all(cls):
        """Get all UPS devices, ordered by order_index."""
        return cls.query.order_by(cls.order_index).all()

    @classmethod
    def get_primary(cls):
        """Get the primary UPS device."""
        primary = cls.query.filter_by(is_primary=True, is_enabled=True).first()
        if not primary:
            # Fallback to first enabled device
            primary = cls.query.filter_by(is_enabled=True).order_by(cls.order_index).first()
        return primary

    @classmethod
    def get_by_name(cls, name):
        """Get UPS device by name."""
        return cls.query.filter_by(name=name).first()

    @classmethod
    def get_by_id(cls, ups_id):
        """Get UPS device by ID."""
        return cls.query.filter_by(id=ups_id).first()

    def update_last_seen(self):
        """Update the last_seen_at timestamp."""
        from core.db.ups import db as app_db
        self.last_seen_at = datetime.now(pytz.UTC)
        app_db.session.commit()
        if logger:
            logger.debug(f"✅ Updated last_seen for UPS {self.name}")

    def get_driver_options_dict(self):
        """Parse driver_options JSON string to dictionary."""
        if not self.driver_options:
            return {}
        try:
            return json.loads(self.driver_options)
        except Exception as e:
            if logger:
                logger.error(f"❌ Error parsing driver_options for UPS {self.name}: {str(e)}")
            return {}

    def set_driver_options_dict(self, options_dict):
        """Convert dictionary to JSON string and store in driver_options."""
        try:
            self.driver_options = json.dumps(options_dict)
        except Exception as e:
            if logger:
                logger.error(f"❌ Error setting driver_options for UPS {self.name}: {str(e)}")

    @classmethod
    def create_device(cls, **kwargs):
        """
        Create a new UPS device.

        Args:
            **kwargs: UPS device parameters

        Returns:
            UPSDevice: The created device
        """
        try:
            from core.db.ups import db as app_db

            new_device = cls(**kwargs)
            app_db.session.add(new_device)
            app_db.session.commit()

            if logger:
                logger.info(f"✅ Created new UPS device: {new_device.name}")

            return new_device

        except Exception as e:
            try:
                app_db.session.rollback()
            except:
                pass
            if logger:
                logger.error(f"❌ Error creating UPS device: {str(e)}")
            raise

    @classmethod
    def update_device(cls, ups_id, **kwargs):
        """
        Update an existing UPS device.

        Args:
            ups_id: ID of the UPS device
            **kwargs: Fields to update

        Returns:
            UPSDevice: The updated device
        """
        try:
            from core.db.ups import db as app_db

            device = cls.get_by_id(ups_id)
            if not device:
                raise ValueError(f"UPS device with ID {ups_id} not found")

            for key, value in kwargs.items():
                if hasattr(device, key):
                    setattr(device, key, value)

            device.updated_at = datetime.now(pytz.UTC)
            app_db.session.commit()

            if logger:
                logger.info(f"✅ Updated UPS device: {device.name}")

            return device

        except Exception as e:
            try:
                app_db.session.rollback()
            except:
                pass
            if logger:
                logger.error(f"❌ Error updating UPS device: {str(e)}")
            raise

    @classmethod
    def delete_device(cls, ups_id):
        """
        Delete a UPS device.

        Args:
            ups_id: ID of the UPS device
        """
        try:
            from core.db.ups import db as app_db

            # Ensure we're not deleting the only device
            total_devices = cls.query.count()
            if total_devices <= 1:
                raise ValueError("Cannot delete the only UPS device")

            device = cls.get_by_id(ups_id)
            if not device:
                raise ValueError(f"UPS device with ID {ups_id} not found")

            device_name = device.name
            app_db.session.delete(device)
            app_db.session.commit()

            if logger:
                logger.info(f"✅ Deleted UPS device: {device_name}")

        except Exception as e:
            try:
                app_db.session.rollback()
            except:
                pass
            if logger:
                logger.error(f"❌ Error deleting UPS device: {str(e)}")
            raise


def init_model(model_base, db_logger=None):
    """
    Initialize the ORM model for UPS devices.

    Args:
        model_base: SQLAlchemy model base class
        db_logger: Logger instance or function to get logger

    Returns:
        class: Initialized UPSDeviceModel class
    """
    global db, logger

    # Set the database logger
    from core.logger import database_logger
    logger = database_logger

    class UPSDeviceModel(model_base, UPSDevice):
        """ORM model for UPS devices"""
        __table_args__ = {'extend_existing': True}

    return UPSDeviceModel
