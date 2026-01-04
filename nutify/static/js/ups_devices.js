/**
 * UPS Devices Management Page JavaScript
 *
 * Handles CRUD operations for UPS devices:
 * - Add new devices
 * - Edit existing devices
 * - Delete devices
 * - Enable/disable devices
 * - Test connections
 */

// Global state
let currentEditingDeviceId = null;

/**
 * Initialize the page
 */
document.addEventListener('DOMContentLoaded', function() {
    setupEventListeners();
    loadDevices();
});

/**
 * Setup all event listeners
 */
function setupEventListeners() {
    // Add device button
    const addDeviceBtn = document.getElementById('addDeviceBtn');
    if (addDeviceBtn) {
        addDeviceBtn.addEventListener('click', showAddDeviceModal);
    }

    const addFirstDeviceBtn = document.getElementById('addFirstDeviceBtn');
    if (addFirstDeviceBtn) {
        addFirstDeviceBtn.addEventListener('click', showAddDeviceModal);
    }

    // Refresh button
    const refreshBtn = document.getElementById('refreshDevicesBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadDevices);
    }

    // Modal close buttons
    const closeBtn = document.getElementById('closeDeviceModal');
    if (closeBtn) {
        closeBtn.addEventListener('click', hideDeviceModal);
    }

    const cancelBtn = document.getElementById('cancelDeviceModal');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', hideDeviceModal);
    }

    const overlay = document.querySelector('#deviceModal .modal-overlay');
    if (overlay) {
        overlay.addEventListener('click', hideDeviceModal);
    }

    // Save device button
    const saveBtn = document.getElementById('saveDeviceBtn');
    if (saveBtn) {
        saveBtn.addEventListener('click', saveDevice);
    }

    // Device action buttons (delegated event handling)
    document.addEventListener('click', function(e) {
        // Edit device
        if (e.target.closest('.edit_device')) {
            e.preventDefault();
            const deviceId = e.target.closest('.edit_device').dataset.deviceId;
            showEditDeviceModal(deviceId);
        }

        // Test connection
        if (e.target.closest('.test_connection')) {
            e.preventDefault();
            const deviceId = e.target.closest('.test_connection').dataset.deviceId;
            testConnection(deviceId);
        }

        // Toggle device
        if (e.target.closest('.toggle_device')) {
            e.preventDefault();
            const deviceId = e.target.closest('.toggle_device').dataset.deviceId;
            toggleDevice(deviceId);
        }

        // Delete device
        if (e.target.closest('.delete_device')) {
            e.preventDefault();
            const deviceId = e.target.closest('.delete_device').dataset.deviceId;
            deleteDevice(deviceId);
        }

        // Dropdown menu toggle
        if (e.target.closest('.ups_device_menu_btn')) {
            e.preventDefault();
            const dropdown = e.target.closest('.ups_device_actions_dropdown');
            dropdown.classList.toggle('active');
        }
    });

    // Close dropdowns when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.ups_device_actions_dropdown')) {
            document.querySelectorAll('.ups_device_actions_dropdown.active').forEach(dropdown => {
                dropdown.classList.remove('active');
            });
        }
    });
}

/**
 * Load all devices from the API
 */
function loadDevices() {
    fetch('/ups-management/api/devices')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                console.log(`Loaded ${data.count} UPS devices`);
                // Update stats
                updateStats(data.devices);
                // Could update device cards here if needed
            } else {
                showAlert('Failed to load devices: ' + data.message, 'error');
            }
        })
        .catch(error => {
            console.error('Error loading devices:', error);
            showAlert('Error loading devices', 'error');
        });
}

/**
 * Update statistics display
 */
function updateStats(devices) {
    const totalDevices = devices.length;
    const enabledDevices = devices.filter(d => d.is_enabled).length;
    const disabledDevices = totalDevices - enabledDevices;
    const primaryDevice = devices.find(d => d.is_primary);

    document.getElementById('totalDevices').textContent = totalDevices;
    document.getElementById('enabledDevices').textContent = enabledDevices;
    document.getElementById('disabledDevices').textContent = disabledDevices;

    if (primaryDevice) {
        document.getElementById('primaryDevice').textContent = primaryDevice.friendly_name || primaryDevice.name;
    }
}

/**
 * Show add device modal
 */
function showAddDeviceModal() {
    currentEditingDeviceId = null;
    document.getElementById('modalTitle').textContent = 'Add UPS Device';
    document.getElementById('deviceForm').reset();
    document.getElementById('deviceId').value = '';
    document.getElementById('deviceHost').value = 'localhost';
    document.getElementById('deviceIsEnabled').checked = true;
    showModal('deviceModal');
}

/**
 * Show edit device modal
 */
function showEditDeviceModal(deviceId) {
    currentEditingDeviceId = deviceId;
    document.getElementById('modalTitle').textContent = 'Edit UPS Device';

    // Fetch device details
    fetch('/ups-management/api/devices')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                const device = data.devices.find(d => d.id == deviceId);
                if (device) {
                    // Populate form
                    document.getElementById('deviceId').value = device.id;
                    document.getElementById('deviceName').value = device.name;
                    document.getElementById('deviceFriendlyName').value = device.friendly_name || '';
                    document.getElementById('deviceDriver').value = device.driver;
                    document.getElementById('devicePort').value = device.port;
                    document.getElementById('deviceHost').value = device.host;
                    document.getElementById('deviceDescription').value = device.description || '';
                    document.getElementById('deviceIsPrimary').checked = device.is_primary;
                    document.getElementById('deviceIsEnabled').checked = device.is_enabled;

                    showModal('deviceModal');
                }
            }
        })
        .catch(error => {
            console.error('Error loading device:', error);
            showAlert('Error loading device details', 'error');
        });
}

/**
 * Hide device modal
 */
function hideDeviceModal() {
    hideModal('deviceModal');
}

/**
 * Save device (add or update)
 */
function saveDevice() {
    const deviceId = document.getElementById('deviceId').value;
    const isEdit = deviceId && deviceId !== '';

    const deviceData = {
        name: document.getElementById('deviceName').value,
        friendly_name: document.getElementById('deviceFriendlyName').value,
        driver: document.getElementById('deviceDriver').value,
        port: document.getElementById('devicePort').value,
        host: document.getElementById('deviceHost').value,
        description: document.getElementById('deviceDescription').value,
        is_primary: document.getElementById('deviceIsPrimary').checked,
        is_enabled: document.getElementById('deviceIsEnabled').checked
    };

    // Validate required fields
    if (!deviceData.name || !deviceData.driver || !deviceData.port) {
        showAlert('Please fill in all required fields', 'error');
        return;
    }

    const url = isEdit
        ? `/ups-management/api/update/${deviceId}`
        : '/ups-management/api/add';

    const method = isEdit ? 'PUT' : 'POST';

    fetch(url, {
        method: method,
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(deviceData)
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showAlert(data.message, 'success');
                hideDeviceModal();
                // Reload page to show updated devices
                setTimeout(() => {
                    window.location.reload();
                }, 1000);
            } else {
                showAlert(data.message, 'error');
            }
        })
        .catch(error => {
            console.error('Error saving device:', error);
            showAlert('Error saving device', 'error');
        });
}

/**
 * Toggle device enabled state
 */
function toggleDevice(deviceId) {
    if (!confirm('Are you sure you want to toggle this device?')) {
        return;
    }

    fetch(`/ups-management/api/toggle/${deviceId}`, {
        method: 'POST'
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showAlert(data.message, 'success');
                // Reload page to show updated status
                setTimeout(() => {
                    window.location.reload();
                }, 1000);
            } else {
                showAlert(data.message, 'error');
            }
        })
        .catch(error => {
            console.error('Error toggling device:', error);
            showAlert('Error toggling device', 'error');
        });
}

/**
 * Delete device
 */
function deleteDevice(deviceId) {
    if (!confirm('Are you sure you want to delete this UPS device? This cannot be undone.')) {
        return;
    }

    fetch(`/ups-management/api/delete/${deviceId}`, {
        method: 'DELETE'
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showAlert(data.message, 'success');
                // Reload page to show updated devices
                setTimeout(() => {
                    window.location.reload();
                }, 1000);
            } else {
                showAlert(data.message, 'error');
            }
        })
        .catch(error => {
            console.error('Error deleting device:', error);
            showAlert('Error deleting device', 'error');
        });
}

/**
 * Test connection to a device
 */
function testConnection(deviceId) {
    showAlert('Testing connection...', 'info');

    fetch(`/ups-management/api/test-connection/${deviceId}`, {
        method: 'POST'
    })
        .then(response => response.json())
        .then(data => {
            if (data.connected) {
                showAlert(`Connection successful! Status: ${data.ups_status}`, 'success');

                // Update status indicator on the card
                const statusIndicator = document.getElementById(`status-${deviceId}`);
                if (statusIndicator) {
                    statusIndicator.querySelector('.status_text').textContent = data.ups_status;
                    statusIndicator.classList.add('connected');
                }
            } else {
                showAlert(data.message, 'warning');
            }
        })
        .catch(error => {
            console.error('Error testing connection:', error);
            showAlert('Error testing connection', 'error');
        });
}

/**
 * Show a modal
 */
function showModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('show');
    }
}

/**
 * Hide a modal
 */
function hideModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('show');
    }
}

/**
 * Show an alert message
 */
function showAlert(message, type) {
    // Check if notifications system exists
    if (typeof window.showNotification === 'function') {
        window.showNotification(message, type);
    } else {
        // Fallback to console
        console.log(`[${type.toUpperCase()}] ${message}`);
        alert(message);
    }
}
