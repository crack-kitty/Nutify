import os
import re
from flask import current_app
from jinja2 import Environment, FileSystemLoader, Template

class NUTConfManager:
    """
    Manager for NUT configuration files that uses template files
    to generate the appropriate configuration based on the NUT mode
    and user inputs.
    """
    
    def __init__(self, templates_dir):
        """
        Initialize the configuration manager.
        
        Args:
            templates_dir: Path to the directory containing template files
        """
        self.templates_dir = templates_dir
    
    def get_template_path(self, filename, mode):
        """
        Get the path to the appropriate template file based on the mode.
        
        Args:
            filename: Base filename (e.g., 'nut.conf', 'ups.conf')
            mode: NUT mode ('standalone', 'netserver', 'netclient')
            
        Returns:
            Path to the template file
        """
        # Try mode-specific template first
        template_path = os.path.join(self.templates_dir, f"{filename}.{mode}")
        
        # If it doesn't exist, fall back to the empty template for netclient mode
        if not os.path.exists(template_path) and mode == 'netclient':
            template_path = os.path.join(self.templates_dir, f"{filename}.empty")
            
            # If empty template doesn't exist, log an error
            if not os.path.exists(template_path):
                current_app.logger.error(f"No template found for {filename} in {mode} mode")
                return None
        
        # If file exists, return the path
        if os.path.exists(template_path):
            return template_path
        
        # If no template found, log error
        current_app.logger.error(f"No template found for {filename} in {mode} mode")
        return None
    
    def render_template(self, template_path, variables):
        """
        Render a template by replacing variables with their values.
        
        Args:
            template_path: Path to the template file
            variables: Dictionary of variables to replace
            
        Returns:
            Rendered template content
        """
        if not template_path or not os.path.exists(template_path):
            return ""
        
        try:
            with open(template_path, 'r') as f:
                content = f.read()
            
            # Log variables for debugging
            current_app.logger.debug(f"Rendering template {template_path}")
            current_app.logger.debug(f"Variables: {variables}")
            
            # Replace variables in the template
            for key, value in variables.items():
                placeholder = f"{{{{%s}}}}" % key
                if placeholder in content:
                    current_app.logger.debug(f"Replacing {placeholder} with {value}")
                    content = content.replace(placeholder, str(value))
                else:
                    current_app.logger.debug(f"Placeholder {placeholder} not found in template")
            
            # Check for any remaining unmatched placeholders
            remaining_placeholders = re.findall(r'{{([^}]+)}}', content)
            if remaining_placeholders:
                current_app.logger.warning(f"Unmatched placeholders in template {template_path}: {remaining_placeholders}")
                
                # Auto-replace common placeholders with sensible defaults
                common_defaults = {
                    'ADMIN_USERNAME': 'admin',
                    'ADMIN_PASSWORD': 'adminpass',
                    'MONITOR_USERNAME': 'monuser',
                    'MONITOR_PASSWORD': 'monpass',
                    'UPS_NAME': 'ups',
                    'DRIVER': 'usbhid-ups',
                    'PORT': 'auto',
                    'DESCRIPTION': 'UPS',
                    'ADDITIONAL_USERS': ''
                }
                
                for placeholder in remaining_placeholders:
                    if placeholder in common_defaults:
                        default_value = common_defaults[placeholder]
                        current_app.logger.warning(f"Auto-replacing {placeholder} with default: {default_value}")
                        content = content.replace(f"{{{{{placeholder}}}}}", default_value)
            
            return content
        except Exception as e:
            current_app.logger.error(f"Error rendering template {template_path}: {e}")
            return ""
    
    def get_conf_files(self, mode, variables):
        """
        Get all configuration files for the specified mode with variables replaced.
        
        Args:
            mode: NUT mode ('standalone', 'netserver', 'netclient')
            variables: Dictionary of variables to replace in templates
            
        Returns:
            Dictionary of configuration files with their content
        """
        conf_files = {
            'nut.conf': '',
            'ups.conf': '',
            'upsd.conf': '',
            'upsd.users': '',
            'upsmon.conf': ''
        }
        
        # For each configuration file, get the appropriate template and render it
        for filename in conf_files.keys():
            template_path = self.get_template_path(filename, mode)
            if template_path:
                conf_files[filename] = self.render_template(template_path, variables)
        
        return conf_files
    
    def validate_mode(self, mode):
        """
        Validate that the NUT mode is supported.
        
        Args:
            mode: NUT mode to validate
            
        Returns:
            True if valid, False otherwise
        """
        valid_modes = ['standalone', 'netserver', 'netclient']
        return mode in valid_modes
    
    def clean_variable_name(self, value):
        """
        Clean a value to be safe for use in a configuration file.

        Args:
            value: Value to clean

        Returns:
            Cleaned value
        """
        if value is None:
            return ""

        # Basic cleaning to prevent injection
        value = str(value)
        value = value.replace('"', '\\"')  # Escape double quotes
        return value

    def render_jinja2_template(self, template_path, variables):
        """
        Render a template using Jinja2 template engine.

        Args:
            template_path: Path to the template file
            variables: Dictionary of variables to pass to template

        Returns:
            Rendered template content
        """
        if not template_path or not os.path.exists(template_path):
            return ""

        try:
            # Create Jinja2 environment
            template_dir = os.path.dirname(template_path)
            template_name = os.path.basename(template_path)

            env = Environment(loader=FileSystemLoader(template_dir))
            template = env.get_template(template_name)

            # Render the template
            content = template.render(**variables)

            current_app.logger.debug(f"Rendered Jinja2 template {template_path}")
            return content

        except Exception as e:
            current_app.logger.error(f"Error rendering Jinja2 template {template_path}: {e}")
            return ""

    def get_multi_ups_conf_files(self, mode, ups_devices, global_vars=None):
        """
        Generate configuration files for multiple UPS devices using Jinja2 templates.

        Args:
            mode: NUT mode ('standalone', 'netserver', 'netclient')
            ups_devices: List of dictionaries containing UPS device configurations.
                        Each dict should have: name, driver, port, host, description, etc.
            global_vars: Dictionary of global variables (admin creds, server settings, etc.)

        Returns:
            Dictionary of configuration files with their content
        """
        if global_vars is None:
            global_vars = {}

        # Prepare template variables
        template_vars = {
            'UPS_DEVICES': ups_devices,
            'ADMIN_USERNAME': global_vars.get('admin_username', 'admin'),
            'ADMIN_PASSWORD': global_vars.get('admin_password', 'adminpass'),
            'MONITOR_USERNAME': global_vars.get('monitor_username', 'monuser'),
            'MONITOR_PASSWORD': global_vars.get('monitor_password', 'monpass'),
            'SERVER_ADDRESS': global_vars.get('server_address', '127.0.0.1'),
            'LISTEN_ADDRESS': global_vars.get('listen_address', '0.0.0.0'),
            'LISTEN_PORT': global_vars.get('listen_port', '3493'),
            'ADDITIONAL_USERS': global_vars.get('additional_users', ''),
        }

        # Add backward compatibility for single UPS variables
        if ups_devices and len(ups_devices) > 0:
            first_ups = ups_devices[0]
            template_vars.update({
                'UPS_NAME': first_ups.get('name', 'ups'),
                'DRIVER': first_ups.get('driver', 'usbhid-ups'),
                'PORT': first_ups.get('port', 'auto'),
                'DESCRIPTION': first_ups.get('description', 'UPS'),
                'UPS_HOST': first_ups.get('host', 'localhost'),
            })

        conf_files = {}

        # Render each configuration file
        for filename in ['nut.conf', 'ups.conf', 'upsd.conf', 'upsd.users', 'upsmon.conf']:
            template_path = self.get_template_path(filename, mode)
            if template_path:
                # Use Jinja2 for rendering (supports loops and conditionals)
                conf_files[filename] = self.render_jinja2_template(template_path, template_vars)

                # Fallback to simple rendering if Jinja2 fails or for non-Jinja2 templates
                if not conf_files[filename]:
                    conf_files[filename] = self.render_template(template_path, template_vars)

        return conf_files

    def load_ups_devices_from_db(self):
        """
        Load enabled UPS devices from the database.

        Returns:
            List of UPS device dictionaries
        """
        try:
            from core.db.ups import db
            from sqlalchemy import text

            result = db.session.execute(text("""
                SELECT id, name, friendly_name, driver, port, host,
                       description, vendor_id, product_id, serial
                FROM ups_devices
                WHERE is_enabled = 1
                ORDER BY order_index
            """))

            devices = []
            for row in result:
                device = {
                    'id': row[0],
                    'name': row[1],
                    'friendly_name': row[2] or row[1],
                    'driver': row[3],
                    'port': row[4],
                    'host': row[5] or 'localhost',
                    'description': row[6] or row[1],
                    'vendor_id': row[7],
                    'product_id': row[8],
                    'serial': row[9],
                }
                devices.append(device)

            return devices

        except Exception as e:
            current_app.logger.error(f"Error loading UPS devices from database: {e}")
            return []

    def regenerate_configs_from_db(self, mode=None):
        """
        Regenerate all NUT configuration files from database.

        Args:
            mode: NUT mode (if None, will read from current nut.conf)

        Returns:
            Dictionary of configuration files
        """
        # Get current mode if not specified
        if mode is None:
            mode = self.get_current_nut_mode()

        # Load UPS devices from database
        ups_devices = self.load_ups_devices_from_db()

        if not ups_devices:
            current_app.logger.warning("No enabled UPS devices found in database")
            return {}

        # Generate configs
        global_vars = {
            'admin_username': 'admin',
            'admin_password': 'adminpass',
            'monitor_username': 'monuser',
            'monitor_password': 'monpass',
        }

        return self.get_multi_ups_conf_files(mode, ups_devices, global_vars)

    def get_current_nut_mode(self):
        """
        Read the current NUT mode from nut.conf file.

        Returns:
            Current NUT mode string or 'standalone' as default
        """
        try:
            nut_conf_path = '/etc/nut/nut.conf'
            if os.path.exists(nut_conf_path):
                with open(nut_conf_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('MODE=') and not line.startswith('#'):
                            mode = line.split('=', 1)[1].strip().strip('"\'')
                            return mode
            return 'standalone'
        except Exception as e:
            current_app.logger.error(f"Error reading NUT mode: {e}")
            return 'standalone' 