"""
UPS Management API Routes.

This module provides REST API endpoints for managing UPS devices.
"""

from flask import jsonify, request
from core.ups_management import ups_management_bp
from core.logger import database_logger as logger
from core.db.ups import db
from core.db.orm import UPSDevice
from core.nut_config.conf_manager import NUTConfManager
from core.db.ups.utils import ups_config_manager
import os
import subprocess


@ups_management_bp.route('/api/devices', methods=['GET'])
def get_devices():
    """
    Get all UPS devices.

    Returns:
        JSON: List of all UPS devices with their details
    """
    try:
        devices = UPSDevice.query.order_by(UPSDevice.order_index, UPSDevice.id).all()

        devices_list = []
        for device in devices:
            devices_list.append({
                'id': device.id,
                'name': device.name,
                'friendly_name': device.friendly_name,
                'driver': device.driver,
                'port': device.port,
                'host': device.host,
                'description': device.description,
                'is_enabled': device.is_enabled,
                'is_primary': device.is_primary,
                'connection_type': device.connection_type,
                'vendor_id': device.vendor_id,
                'product_id': device.product_id,
                'serial': device.serial,
                'order_index': device.order_index
            })

        return jsonify({
            'status': 'success',
            'devices': devices_list,
            'count': len(devices_list)
        })

    except Exception as e:
        logger.error(f"❌ Error retrieving UPS devices: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error retrieving devices: {str(e)}'
        }), 500


@ups_management_bp.route('/api/add', methods=['POST'])
def add_device():
    """
    Add a new UPS device.

    Returns:
        JSON: Status and new device ID
    """
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['name', 'driver', 'port']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'status': 'error',
                    'message': f'Missing required field: {field}'
                }), 400

        # Check for duplicate name
        existing = UPSDevice.query.filter_by(name=data['name']).first()
        if existing:
            return jsonify({
                'status': 'error',
                'message': f'UPS device with name "{data["name"]}" already exists'
            }), 400

        # Create new UPS device
        new_device = UPSDevice.create_device(
            name=data['name'],
            friendly_name=data.get('friendly_name', data['name']),
            driver=data['driver'],
            port=data['port'],
            host=data.get('host', 'localhost'),
            description=data.get('description', ''),
            is_enabled=data.get('is_enabled', True),
            is_primary=data.get('is_primary', False),
            connection_type=data.get('connection_type', 'local_usb'),
            vendor_id=data.get('vendor_id'),
            product_id=data.get('product_id'),
            serial=data.get('serial')
        )

        logger.info(f"✅ Added new UPS device: {new_device.name} (ID: {new_device.id})")

        # Regenerate NUT configuration files
        regenerate_nut_configs()

        # Reload UPS config manager
        ups_config_manager.reload()

        return jsonify({
            'status': 'success',
            'message': f'UPS device "{new_device.friendly_name}" added successfully',
            'device_id': new_device.id
        })

    except Exception as e:
        logger.error(f"❌ Error adding UPS device: {str(e)}")
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'Error adding device: {str(e)}'
        }), 500


@ups_management_bp.route('/api/update/<int:ups_id>', methods=['PUT'])
def update_device(ups_id):
    """
    Update an existing UPS device.

    Args:
        ups_id: ID of the UPS device to update

    Returns:
        JSON: Status message
    """
    try:
        data = request.get_json()

        # Update the device
        success = UPSDevice.update_device(ups_id, **data)

        if not success:
            return jsonify({
                'status': 'error',
                'message': f'UPS device with ID {ups_id} not found'
            }), 404

        logger.info(f"✅ Updated UPS device ID {ups_id}")

        # Regenerate NUT configuration files
        regenerate_nut_configs()

        # Reload UPS config manager
        ups_config_manager.reload()

        return jsonify({
            'status': 'success',
            'message': 'UPS device updated successfully'
        })

    except Exception as e:
        logger.error(f"❌ Error updating UPS device {ups_id}: {str(e)}")
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'Error updating device: {str(e)}'
        }), 500


@ups_management_bp.route('/api/toggle/<int:ups_id>', methods=['POST'])
def toggle_device(ups_id):
    """
    Enable or disable a UPS device.

    Args:
        ups_id: ID of the UPS device to toggle

    Returns:
        JSON: Status and new enabled state
    """
    try:
        device = UPSDevice.query.get(ups_id)

        if not device:
            return jsonify({
                'status': 'error',
                'message': f'UPS device with ID {ups_id} not found'
            }), 404

        # Toggle the enabled state
        new_state = not device.is_enabled

        # Prevent disabling the last enabled device
        if not new_state:
            enabled_count = UPSDevice.query.filter_by(is_enabled=True).count()
            if enabled_count <= 1:
                return jsonify({
                    'status': 'error',
                    'message': 'Cannot disable the last enabled UPS device'
                }), 400

        # Update the device
        device.is_enabled = new_state
        db.session.commit()

        logger.info(f"✅ {'Enabled' if new_state else 'Disabled'} UPS device: {device.name}")

        # Regenerate NUT configuration files (will exclude disabled devices)
        regenerate_nut_configs()

        # Reload UPS config manager
        ups_config_manager.reload()

        return jsonify({
            'status': 'success',
            'message': f'UPS device {"enabled" if new_state else "disabled"} successfully',
            'is_enabled': new_state
        })

    except Exception as e:
        logger.error(f"❌ Error toggling UPS device {ups_id}: {str(e)}")
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'Error toggling device: {str(e)}'
        }), 500


@ups_management_bp.route('/api/delete/<int:ups_id>', methods=['DELETE'])
def delete_device(ups_id):
    """
    Delete a UPS device.

    Args:
        ups_id: ID of the UPS device to delete

    Returns:
        JSON: Status message
    """
    try:
        # Check if this is the last UPS device
        total_count = UPSDevice.query.count()
        if total_count <= 1:
            return jsonify({
                'status': 'error',
                'message': 'Cannot delete the last UPS device'
            }), 400

        # Delete the device
        success = UPSDevice.delete_device(ups_id)

        if not success:
            return jsonify({
                'status': 'error',
                'message': f'UPS device with ID {ups_id} not found'
            }), 404

        logger.info(f"✅ Deleted UPS device ID {ups_id}")

        # Regenerate NUT configuration files
        regenerate_nut_configs()

        # Reload UPS config manager
        ups_config_manager.reload()

        return jsonify({
            'status': 'success',
            'message': 'UPS device deleted successfully'
        })

    except Exception as e:
        logger.error(f"❌ Error deleting UPS device {ups_id}: {str(e)}")
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'Error deleting device: {str(e)}'
        }), 500


@ups_management_bp.route('/api/test-connection/<int:ups_id>', methods=['POST'])
def test_connection(ups_id):
    """
    Test connection to a UPS device.

    Args:
        ups_id: ID of the UPS device to test

    Returns:
        JSON: Connection test results
    """
    try:
        device = UPSDevice.query.get(ups_id)

        if not device:
            return jsonify({
                'status': 'error',
                'message': f'UPS device with ID {ups_id} not found'
            }), 404

        # Test connection using upsc command
        from core.settings import UPSC_BIN

        ups_target = f"{device.name}@{device.host}"
        result = subprocess.run(
            [UPSC_BIN, ups_target],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            # Parse UPS status from output
            status_line = ""
            for line in result.stdout.splitlines():
                if 'ups.status:' in line:
                    status_line = line.split(':', 1)[1].strip()
                    break

            return jsonify({
                'status': 'success',
                'message': f'Successfully connected to {device.friendly_name}',
                'ups_status': status_line or 'ONLINE',
                'connected': True
            })
        else:
            return jsonify({
                'status': 'warning',
                'message': f'Could not connect to {device.friendly_name}: {result.stderr.strip()}',
                'connected': False
            })

    except subprocess.TimeoutExpired:
        return jsonify({
            'status': 'error',
            'message': 'Connection test timed out',
            'connected': False
        }), 408

    except Exception as e:
        logger.error(f"❌ Error testing connection to UPS {ups_id}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error testing connection: {str(e)}',
            'connected': False
        }), 500


def regenerate_nut_configs():
    """
    Regenerate all NUT configuration files from the database.

    This function is called after any UPS device change to ensure
    the NUT configuration files are kept in sync with the database.
    """
    try:
        from core.nut_config.conf_manager import NUTConfManager

        # Get the templates directory
        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'nut_config',
            'conf_templates'
        )

        conf_manager = NUTConfManager(templates_dir)

        # Regenerate configs from database
        conf_files = conf_manager.regenerate_configs_from_db()

        if not conf_files:
            logger.warning("⚠️ No configuration files generated")
            return False

        # Write configuration files to /etc/nut/
        config_dir = '/etc/nut'
        for filename, content in conf_files.items():
            filepath = os.path.join(config_dir, filename)
            with open(filepath, 'w') as f:
                f.write(content)
            logger.debug(f"✅ Regenerated {filename}")

        logger.info("✅ NUT configuration files regenerated successfully")

        # Restart NUT services to apply changes
        restart_nut_services()

        return True

    except Exception as e:
        logger.error(f"❌ Error regenerating NUT configs: {str(e)}")
        return False


def restart_nut_services():
    """
    Restart NUT services to apply configuration changes.
    """
    try:
        # Stop UPS drivers
        subprocess.run(['upsdrvctl', 'stop'], capture_output=True, timeout=10)

        # Start UPS drivers
        subprocess.run(['upsdrvctl', 'start'], capture_output=True, timeout=10)

        # Reload upsd
        subprocess.run(['upsd', '-c', 'reload'], capture_output=True, timeout=10)

        logger.info("✅ NUT services restarted successfully")

    except Exception as e:
        logger.warning(f"⚠️ Error restarting NUT services: {str(e)}")
