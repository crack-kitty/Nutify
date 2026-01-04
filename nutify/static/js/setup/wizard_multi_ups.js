/**
 * Multi-UPS Support Extension for Setup Wizard
 *
 * This module extends the setup wizard to support selecting and configuring
 * multiple UPS devices during initial setup.
 */

// Track selected devices per mode
const selectedDevices = {
    'standalone': [],
    'netserver': []
};

/**
 * Render a scan device with checkbox for multi-select
 */
function renderMultiSelectDevice(device, mode, scanResults) {
    const deviceElement = document.createElement('div');
    deviceElement.className = 'scan-device';
    deviceElement.__device = device;

    // Create checkbox for multi-select
    const deviceId = `device-${mode}-${device.name || Math.random()}`;

    deviceElement.innerHTML = `
        <div class="device-checkbox-wrapper">
            <input type="checkbox" class="device-checkbox" id="${deviceId}" />
            <label for="${deviceId}" class="device-label">
                <div class="scan-device-content">
                    <div class="scan-device-name">${device.name || 'Unknown UPS'}</div>
                    <div class="scan-device-details">
                        ${device.model ? `<strong>${device.model}</strong><br>` : ''}
                        Driver: ${device.driver || 'Unknown'}<br>
                        Port: ${device.port || 'Unknown'}
                        ${device.serial ? `<br>Serial: ${device.serial}` : ''}
                    </div>
                </div>
            </label>
            <button class="device-config-btn" type="button" data-device-id="${deviceId}">
                <i class="fas fa-cog"></i> Configure
            </button>
        </div>
    `;

    // Checkbox change handler
    const checkbox = deviceElement.querySelector('.device-checkbox');
    checkbox.addEventListener('change', function() {
        if (this.checked) {
            // Add device to selected list
            if (!selectedDevices[mode].find(d => d.name === device.name)) {
                selectedDevices[mode].push(device);
                deviceElement.classList.add('selected');
            }
        } else {
            // Remove device from selected list
            selectedDevices[mode] = selectedDevices[mode].filter(d => d.name !== device.name);
            deviceElement.classList.remove('selected');
        }

        updateSelectedDevicesDisplay(mode);
    });

    // Configure button handler
    const configBtn = deviceElement.querySelector('.device-config-btn');
    configBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        showDeviceConfigModal(device, mode, deviceId);
    });

    return deviceElement;
}

/**
 * Update the display of selected devices count
 */
function updateSelectedDevicesDisplay(mode) {
    const count = selectedDevices[mode].length;

    // Update count display
    let countDisplay = document.getElementById(`selected-count-${mode}`);
    if (!countDisplay) {
        countDisplay = document.createElement('div');
        countDisplay.id = `selected-count-${mode}`;
        countDisplay.className = 'selected-devices-count';

        const scanResults = document.getElementById(`scan-results-${mode}`);
        if (scanResults) {
            scanResults.insertAdjacentElement('beforebegin', countDisplay);
        }
    }

    if (count > 0) {
        countDisplay.innerHTML = `
            <div class="selected-summary">
                <i class="fas fa-check-circle"></i>
                <span><strong>${count}</strong> UPS device(s) selected</span>
            </div>
        `;
        countDisplay.classList.remove('hidden');
    } else {
        countDisplay.classList.add('hidden');
    }
}

/**
 * Show modal for configuring individual UPS device
 */
function showDeviceConfigModal(device, mode, deviceId) {
    // Create modal if it doesn't exist
    let modal = document.getElementById('device-config-modal');
    if (!modal) {
        modal = createDeviceConfigModal();
        document.body.appendChild(modal);
    }

    // Populate modal with device data
    document.getElementById('modal-device-name').textContent = device.name || 'UPS Device';
    document.getElementById('modal-ups-name').value = device.name || '';
    document.getElementById('modal-friendly-name').value = device.friendly_name || device.name || '';
    document.getElementById('modal-description').value = device.description || `${device.model || 'UPS'} ${device.vendor || ''}`.trim();
    document.getElementById('modal-realpower-nominal').value = device.realpower_nominal || '';

    // Determine if this should be primary (first device or explicitly set)
    const isPrimary = selectedDevices[mode].length === 0 || device.is_primary;
    document.getElementById('modal-is-primary').checked = isPrimary;

    // Store device reference for saving
    modal.__currentDevice = device;
    modal.__deviceId = deviceId;
    modal.__mode = mode;

    // Show modal
    modal.classList.add('show');
}

/**
 * Create the device configuration modal HTML
 */
function createDeviceConfigModal() {
    const modal = document.createElement('div');
    modal.id = 'device-config-modal';
    modal.className = 'modal';

    modal.innerHTML = `
        <div class="modal-overlay"></div>
        <div class="modal-content">
            <div class="modal-header">
                <h3>Configure <span id="modal-device-name"></span></h3>
                <button class="modal-close" id="close-device-modal">&times;</button>
            </div>

            <div class="modal-body">
                <div class="form-group">
                    <label for="modal-ups-name">UPS Name (NUT identifier)*</label>
                    <input type="text" id="modal-ups-name" class="form-control" required />
                    <small>Used in NUT commands (e.g., 'ups1', 'ups2'). Must be unique.</small>
                </div>

                <div class="form-group">
                    <label for="modal-friendly-name">Friendly Name</label>
                    <input type="text" id="modal-friendly-name" class="form-control" />
                    <small>Display name in UI (e.g., 'Main Office UPS')</small>
                </div>

                <div class="form-group">
                    <label for="modal-description">Description</label>
                    <textarea id="modal-description" class="form-control" rows="2"></textarea>
                </div>

                <div class="form-group">
                    <label for="modal-realpower-nominal">Nominal Power (Watts)</label>
                    <input type="number" id="modal-realpower-nominal" class="form-control" placeholder="1000" />
                    <small>UPS rated power in Watts</small>
                </div>

                <div class="form-group">
                    <label class="checkbox-label">
                        <input type="checkbox" id="modal-is-primary" />
                        Set as primary UPS (receives critical alerts)
                    </label>
                </div>
            </div>

            <div class="modal-footer">
                <button type="button" id="save-device-config" class="btn btn-primary">Save Configuration</button>
                <button type="button" id="cancel-device-modal" class="btn btn-secondary">Cancel</button>
            </div>
        </div>
    `;

    // Event listeners
    modal.querySelector('#close-device-modal').addEventListener('click', () => hideDeviceConfigModal());
    modal.querySelector('#cancel-device-modal').addEventListener('click', () => hideDeviceConfigModal());
    modal.querySelector('.modal-overlay').addEventListener('click', () => hideDeviceConfigModal());
    modal.querySelector('#save-device-config').addEventListener('click', () => saveDeviceConfig());

    return modal;
}

/**
 * Hide the device configuration modal
 */
function hideDeviceConfigModal() {
    const modal = document.getElementById('device-config-modal');
    if (modal) {
        modal.classList.remove('show');
    }
}

/**
 * Save device configuration from modal
 */
function saveDeviceConfig() {
    const modal = document.getElementById('device-config-modal');
    const device = modal.__currentDevice;
    const mode = modal.__mode;

    // Update device with modal values
    device.name = document.getElementById('modal-ups-name').value;
    device.friendly_name = document.getElementById('modal-friendly-name').value;
    device.description = document.getElementById('modal-description').value;
    device.realpower_nominal = document.getElementById('modal-realpower-nominal').value;
    device.is_primary = document.getElementById('modal-is-primary').checked;

    // If set as primary, unset other devices
    if (device.is_primary) {
        selectedDevices[mode].forEach(d => {
            if (d.name !== device.name) {
                d.is_primary = false;
            }
        });
    }

    // Update device in selected list
    const existingIndex = selectedDevices[mode].findIndex(d => d.name === device.name);
    if (existingIndex >= 0) {
        selectedDevices[mode][existingIndex] = device;
    }

    hideDeviceConfigModal();
    showAlert('Device configuration saved', 'success');
}

/**
 * Get all selected devices for a mode
 */
function getSelectedDevices(mode) {
    return selectedDevices[mode] || [];
}

/**
 * Clear all selected devices for a mode
 */
function clearSelectedDevices(mode) {
    selectedDevices[mode] = [];

    // Uncheck all checkboxes
    const scanResults = document.getElementById(`scan-results-${mode}`);
    if (scanResults) {
        scanResults.querySelectorAll('.device-checkbox').forEach(cb => {
            cb.checked = false;
        });
        scanResults.querySelectorAll('.scan-device').forEach(el => {
            el.classList.remove('selected');
        });
    }

    updateSelectedDevicesDisplay(mode);
}

/**
 * Validate that at least one device is selected
 */
function validateDeviceSelection(mode) {
    if (selectedDevices[mode].length === 0) {
        showAlert('Please select at least one UPS device', 'error');
        return false;
    }

    // Validate that all selected devices have unique names
    const names = selectedDevices[mode].map(d => d.name);
    const uniqueNames = new Set(names);
    if (names.length !== uniqueNames.size) {
        showAlert('All UPS devices must have unique names', 'error');
        return false;
    }

    return true;
}

// Export functions for use in main wizard.js
window.MultiUPSWizard = {
    renderMultiSelectDevice,
    updateSelectedDevicesDisplay,
    showDeviceConfigModal,
    getSelectedDevices,
    clearSelectedDevices,
    validateDeviceSelection,
    selectedDevices
};
