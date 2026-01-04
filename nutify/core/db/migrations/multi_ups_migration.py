"""
Multi-UPS Support Migration
Version: 001_multi_ups_support

This migration adds support for multiple UPS devices by:
1. Creating the ups_devices table to store multiple UPS configurations
2. Adding ups_id column to ups_events for per-UPS event tracking
3. Migrating existing single-UPS configuration to the new schema
"""

import logging
import os
import json
from datetime import datetime
from sqlalchemy import text, inspect
from pathlib import Path

logger = logging.getLogger('migration')

MIGRATION_VERSION = '001_multi_ups'

def check_migration_needed(db):
    """
    Check if multi-UPS migration is needed.

    Args:
        db: SQLAlchemy database instance

    Returns:
        bool: True if migration is needed, False otherwise
    """
    try:
        inspector = inspect(db.engine)
        table_names = inspector.get_table_names()

        # Check if ups_devices table exists
        if 'ups_devices' not in table_names:
            logger.info("🔍 Multi-UPS migration needed: ups_devices table not found")
            return True

        # Check if ups_events has ups_id column
        if 'ups_events' in table_names:
            columns = [col['name'] for col in inspector.get_columns('ups_events')]
            if 'ups_id' not in columns:
                logger.info("🔍 Multi-UPS migration needed: ups_events.ups_id column not found")
                return True

        logger.debug("✅ Multi-UPS schema already up to date")
        return False

    except Exception as e:
        logger.error(f"❌ Error checking migration status: {str(e)}")
        return False

def run_multi_ups_migration(db, app=None):
    """
    Run the multi-UPS migration.

    Args:
        db: SQLAlchemy database instance
        app: Flask application instance (optional, for accessing config)

    Returns:
        bool: True if migration succeeded, False otherwise
    """
    try:
        logger.info("🚀 Starting multi-UPS migration...")

        # Step 1: Create ups_devices table
        if not _create_ups_devices_table(db):
            return False

        # Step 2: Add ups_id to ups_events
        if not _add_ups_id_to_events(db):
            return False

        # Step 3: Migrate existing single-UPS configuration
        if not _migrate_existing_config(db):
            logger.warning("⚠️ No existing UPS configuration found to migrate")

        # Step 4: Mark migration as complete
        _mark_migration_complete(db)

        logger.info("✅ Multi-UPS migration completed successfully")
        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {str(e)}")
        db.session.rollback()
        return False

def _create_ups_devices_table(db):
    """Create the ups_devices table."""
    try:
        logger.info("📊 Creating ups_devices table...")

        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS ups_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(50) NOT NULL UNIQUE,
                friendly_name VARCHAR(100),
                driver VARCHAR(50) NOT NULL,
                port VARCHAR(255) NOT NULL,
                host VARCHAR(255) NOT NULL DEFAULT 'localhost',
                description TEXT,
                is_enabled BOOLEAN NOT NULL DEFAULT 1,
                is_primary BOOLEAN NOT NULL DEFAULT 0,
                connection_type VARCHAR(20),

                vendor_id VARCHAR(10),
                product_id VARCHAR(10),
                serial VARCHAR(100),

                snmp_version VARCHAR(10),
                snmp_community VARCHAR(50),

                baudrate INTEGER,

                driver_options TEXT,

                order_index INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen_at DATETIME,

                CHECK(is_enabled IN (0, 1)),
                CHECK(is_primary IN (0, 1))
            )
        """))

        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_ups_devices_enabled
            ON ups_devices(is_enabled)
        """))

        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_ups_devices_name
            ON ups_devices(name)
        """))

        db.session.commit()
        logger.info("✅ ups_devices table created successfully")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to create ups_devices table: {str(e)}")
        db.session.rollback()
        return False

def _add_ups_id_to_events(db):
    """Add ups_id column to ups_events table."""
    try:
        inspector = inspect(db.engine)

        # Check if ups_events table exists
        if 'ups_events' not in inspector.get_table_names():
            logger.debug("ℹ️ ups_events table doesn't exist yet, skipping ups_id addition")
            return True

        # Check if ups_id column already exists
        columns = [col['name'] for col in inspector.get_columns('ups_events')]
        if 'ups_id' in columns:
            logger.debug("✅ ups_events.ups_id column already exists")
            return True

        logger.info("📊 Adding ups_id column to ups_events table...")

        db.session.execute(text("""
            ALTER TABLE ups_events
            ADD COLUMN ups_id INTEGER REFERENCES ups_devices(id)
        """))

        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_ups_events_ups_id
            ON ups_events(ups_id)
        """))

        db.session.commit()
        logger.info("✅ ups_id column added to ups_events")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to add ups_id to ups_events: {str(e)}")
        db.session.rollback()
        return False

def _migrate_existing_config(db):
    """
    Migrate existing single-UPS configuration to ups_devices table.
    Reads from NUT configuration files and creates the first entry.
    """
    try:
        # Check if ups_devices already has entries
        result = db.session.execute(text("SELECT COUNT(*) FROM ups_devices")).scalar()
        if result > 0:
            logger.info(f"✅ ups_devices table already has {result} entries, skipping migration")
            return True

        logger.info("🔄 Migrating existing single-UPS configuration...")

        # Try to read from NUT configuration files
        ups_config = _parse_nut_config()

        if not ups_config:
            logger.warning("⚠️ No existing NUT configuration found")
            return False

        # Insert the migrated UPS configuration
        db.session.execute(text("""
            INSERT INTO ups_devices (
                name, friendly_name, driver, port, host,
                description, is_enabled, is_primary,
                connection_type, order_index, created_at, updated_at
            ) VALUES (
                :name, :friendly_name, :driver, :port, :host,
                :description, 1, 1,
                :connection_type, 0, :now, :now
            )
        """), {
            'name': ups_config.get('name', 'ups'),
            'friendly_name': ups_config.get('friendly_name', ups_config.get('name', 'UPS')),
            'driver': ups_config.get('driver', 'usbhid-ups'),
            'port': ups_config.get('port', 'auto'),
            'host': ups_config.get('host', 'localhost'),
            'description': ups_config.get('description', 'Migrated from single-UPS setup'),
            'connection_type': ups_config.get('connection_type', 'local_usb'),
            'now': datetime.utcnow()
        })

        db.session.commit()
        logger.info(f"✅ Migrated existing UPS: {ups_config.get('name', 'ups')}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to migrate existing config: {str(e)}")
        db.session.rollback()
        return False

def _parse_nut_config():
    """
    Parse NUT configuration files to extract existing UPS configuration.

    Returns:
        dict: UPS configuration or None if not found
    """
    try:
        # Default NUT config path
        nut_conf_dir = os.environ.get('NUT_CONF_DIR', '/etc/nut')
        ups_conf_path = os.path.join(nut_conf_dir, 'ups.conf')
        upsmon_conf_path = os.path.join(nut_conf_dir, 'upsmon.conf')

        if not os.path.exists(ups_conf_path):
            logger.debug(f"ℹ️ ups.conf not found at {ups_conf_path}")
            return None

        ups_config = {}

        # Parse ups.conf
        with open(ups_conf_path, 'r') as f:
            current_ups = None
            for line in f:
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue

                # UPS section header [ups_name]
                if line.startswith('[') and line.endswith(']'):
                    current_ups = line[1:-1]
                    ups_config['name'] = current_ups
                    continue

                # Parse key = value pairs
                if current_ups and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"')

                    if key == 'driver':
                        ups_config['driver'] = value
                    elif key == 'port':
                        ups_config['port'] = value
                    elif key == 'desc':
                        ups_config['description'] = value

        # Parse upsmon.conf for host
        if os.path.exists(upsmon_conf_path):
            with open(upsmon_conf_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('MONITOR'):
                        # Format: MONITOR ups@localhost 1 user pass master
                        parts = line.split()
                        if len(parts) >= 2:
                            ups_at_host = parts[1]
                            if '@' in ups_at_host:
                                name, host = ups_at_host.split('@', 1)
                                if 'name' not in ups_config:
                                    ups_config['name'] = name
                                ups_config['host'] = host
                            break

        # Set defaults if not found
        if 'name' not in ups_config:
            return None

        ups_config.setdefault('driver', 'usbhid-ups')
        ups_config.setdefault('port', 'auto')
        ups_config.setdefault('host', 'localhost')
        ups_config.setdefault('friendly_name', ups_config['name'])
        ups_config.setdefault('connection_type', 'local_usb')

        logger.info(f"📋 Parsed existing UPS config: {ups_config['name']}")
        return ups_config

    except Exception as e:
        logger.error(f"❌ Error parsing NUT config: {str(e)}")
        return None

def _mark_migration_complete(db):
    """Mark migration as complete in database."""
    try:
        # Create a simple migration tracking table if it doesn't exist
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(50) PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))

        db.session.execute(text("""
            INSERT OR IGNORE INTO schema_migrations (version, applied_at)
            VALUES (:version, :now)
        """), {
            'version': MIGRATION_VERSION,
            'now': datetime.utcnow()
        })

        db.session.commit()
        logger.debug(f"✅ Marked migration {MIGRATION_VERSION} as complete")

    except Exception as e:
        logger.warning(f"⚠️ Could not mark migration as complete: {str(e)}")
