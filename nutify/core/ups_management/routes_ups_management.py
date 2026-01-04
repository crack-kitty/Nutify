"""
UPS Management Page Routes.

This module provides the web page routes for the UPS management interface.
"""

from flask import render_template, redirect, url_for, flash
from core.ups_management import ups_management_bp
from core.logger import database_logger as logger
from core.db.orm import UPSDevice


@ups_management_bp.route('/')
@ups_management_bp.route('/devices')
def list_devices():
    """
    Display all UPS devices with their current status.

    Returns:
        Rendered HTML template showing UPS device grid
    """
    try:
        # Get all UPS devices from database (enabled and disabled)
        devices = UPSDevice.query.order_by(UPSDevice.order_index, UPSDevice.id).all()

        logger.info(f"📋 Displaying {len(devices)} UPS device(s) in management page")

        return render_template(
            'dashboard/ups_devices.html',
            devices=devices,
            page_title='UPS Devices Management'
        )

    except Exception as e:
        logger.error(f"❌ Error loading UPS devices page: {str(e)}")
        flash(f'Error loading UPS devices: {str(e)}', 'error')
        return redirect(url_for('dashboard.main_page'))


@ups_management_bp.route('/add')
def add_device_page():
    """
    Display the add new UPS device page.

    Returns:
        Rendered HTML template for adding a UPS device
    """
    try:
        return render_template(
            'dashboard/ups_add.html',
            page_title='Add UPS Device'
        )

    except Exception as e:
        logger.error(f"❌ Error loading add UPS page: {str(e)}")
        flash(f'Error loading page: {str(e)}', 'error')
        return redirect(url_for('ups_management.list_devices'))


@ups_management_bp.route('/edit/<int:ups_id>')
def edit_device_page(ups_id):
    """
    Display the edit UPS device page.

    Args:
        ups_id: ID of the UPS device to edit

    Returns:
        Rendered HTML template for editing a UPS device
    """
    try:
        device = UPSDevice.query.get(ups_id)

        if not device:
            flash(f'UPS device with ID {ups_id} not found', 'error')
            return redirect(url_for('ups_management.list_devices'))

        return render_template(
            'dashboard/ups_edit.html',
            device=device,
            page_title=f'Edit {device.friendly_name or device.name}'
        )

    except Exception as e:
        logger.error(f"❌ Error loading edit UPS page: {str(e)}")
        flash(f'Error loading page: {str(e)}', 'error')
        return redirect(url_for('ups_management.list_devices'))
