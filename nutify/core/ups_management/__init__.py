"""
UPS Management Module.

This module provides functionality for managing UPS devices after initial setup:
- View all configured UPS devices
- Add new UPS devices
- Edit existing UPS configurations
- Delete UPS devices
- Enable/disable individual UPS devices
"""

from flask import Blueprint

# Create the blueprint
ups_management_bp = Blueprint('ups_management', __name__, url_prefix='/ups-management')

# Import routes to register them with the blueprint
from core.ups_management import routes_ups_management, api_ups_management

__all__ = ['ups_management_bp']
