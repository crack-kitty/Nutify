"""
UPS Data Aggregator Module.

This module provides functions to aggregate metrics from multiple UPS devices
into a unified view for the dashboard.
"""

from core.logger import database_logger as logger


# Status priority for determining worst case (higher number = worse)
STATUS_PRIORITY = {
    'OB DISCHRG': 7,  # On battery, discharging (worst)
    'OB': 6,          # On battery
    'LB': 5,          # Low battery
    'RB': 4,          # Replace battery
    'OVER': 3,        # Overload
    'CHRG': 2,        # Charging
    'OL': 1,          # Online (best)
    'OFFLINE': 8,     # UPS offline (worst case)
    'UNKNOWN': 0      # Unknown status
}


def get_status_priority(status):
    """
    Get priority value for a UPS status string.

    Args:
        status: UPS status string (e.g., 'OL', 'OB DISCHRG')

    Returns:
        int: Priority value (higher = worse)
    """
    if not status:
        return STATUS_PRIORITY['UNKNOWN']

    status = status.upper().strip()

    # Check for exact matches first
    if status in STATUS_PRIORITY:
        return STATUS_PRIORITY[status]

    # Check for composite status (e.g., "OL CHRG")
    max_priority = 0
    for key in STATUS_PRIORITY:
        if key in status:
            max_priority = max(max_priority, STATUS_PRIORITY[key])

    return max_priority if max_priority > 0 else STATUS_PRIORITY['UNKNOWN']


def get_worst_status(statuses):
    """
    Determine the worst status from a list of UPS statuses.

    Args:
        statuses: List of status strings

    Returns:
        str: Worst status string
    """
    if not statuses:
        return 'UNKNOWN'

    worst_status = statuses[0]
    worst_priority = get_status_priority(worst_status)

    for status in statuses[1:]:
        priority = get_status_priority(status)
        if priority > worst_priority:
            worst_priority = priority
            worst_status = status

    return worst_status


def safe_float(value, default=0.0):
    """
    Safely convert value to float.

    Args:
        value: Value to convert
        default: Default value if conversion fails

    Returns:
        float: Converted value or default
    """
    if value is None:
        return default

    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_get(data, key, default=None):
    """
    Safely get value from UPS data object.

    Args:
        data: UPS data object (dict-like or object with attributes)
        key: Key to retrieve
        default: Default value if key doesn't exist

    Returns:
        Value or default
    """
    try:
        # Try dictionary access
        if isinstance(data, dict):
            return data.get(key, default)
        # Try attribute access
        return getattr(data, key, default)
    except (AttributeError, KeyError):
        return default


def aggregate_ups_data(all_ups_data):
    """
    Combine metrics from multiple UPS devices into a unified view.

    This function implements the aggregation strategy:
    - Status: Worst case (OB DISCHRG > OB > LB > RB > CHRG > OL)
    - Power: Sum of all UPS real power
    - Load: Average load percentage
    - Battery: Average battery charge
    - Runtime: Minimum runtime (system limited by shortest)
    - Voltage: Average input/output voltages
    - Counts: Total UPS and online count

    Args:
        all_ups_data: Dictionary of {ups_id: UPSData} or list of UPSData objects

    Returns:
        dict: Aggregated UPS data
    """
    # Convert to list if dict
    if isinstance(all_ups_data, dict):
        ups_list = list(all_ups_data.values())
    else:
        ups_list = list(all_ups_data) if all_ups_data else []

    if not ups_list:
        logger.warning("⚠️ No UPS data to aggregate")
        return {
            'ups_status': 'UNKNOWN',
            'ups_realpower': 0.0,
            'ups_load': 0.0,
            'battery_charge': 0.0,
            'battery_runtime': 0.0,
            'input_voltage': 0.0,
            'output_voltage': 0.0,
            'ups_count': 0,
            'ups_online_count': 0
        }

    # Initialize aggregation variables
    statuses = []
    total_realpower = 0.0
    total_load = 0.0
    total_battery_charge = 0.0
    total_input_voltage = 0.0
    total_output_voltage = 0.0
    min_runtime = None

    online_count = 0
    load_count = 0
    battery_count = 0
    input_voltage_count = 0
    output_voltage_count = 0

    # Aggregate data from all UPS devices
    for ups_data in ups_list:
        # Status
        status = safe_get(ups_data, 'ups_status', safe_get(ups_data, 'ups.status', 'UNKNOWN'))
        statuses.append(status)

        # Count online devices (OL or CHRG indicates online)
        if status and ('OL' in status.upper() or 'CHRG' in status.upper()):
            online_count += 1

        # Real power (sum)
        realpower = safe_float(safe_get(ups_data, 'ups_realpower', safe_get(ups_data, 'ups.realpower', 0)))
        total_realpower += realpower

        # Load percentage (for averaging)
        load = safe_float(safe_get(ups_data, 'ups_load', safe_get(ups_data, 'ups.load', 0)))
        if load > 0:
            total_load += load
            load_count += 1

        # Battery charge (for averaging)
        battery_charge = safe_float(safe_get(ups_data, 'battery_charge', safe_get(ups_data, 'battery.charge', 0)))
        if battery_charge > 0:
            total_battery_charge += battery_charge
            battery_count += 1

        # Battery runtime (minimum)
        runtime = safe_float(safe_get(ups_data, 'battery_runtime', safe_get(ups_data, 'battery.runtime', 0)))
        if runtime > 0:
            if min_runtime is None:
                min_runtime = runtime
            else:
                min_runtime = min(min_runtime, runtime)

        # Input voltage (for averaging)
        input_voltage = safe_float(safe_get(ups_data, 'input_voltage', safe_get(ups_data, 'input.voltage', 0)))
        if input_voltage > 0:
            total_input_voltage += input_voltage
            input_voltage_count += 1

        # Output voltage (for averaging)
        output_voltage = safe_float(safe_get(ups_data, 'output_voltage', safe_get(ups_data, 'output.voltage', 0)))
        if output_voltage > 0:
            total_output_voltage += output_voltage
            output_voltage_count += 1

    # Calculate aggregated values
    ups_count = len(ups_list)
    worst_status = get_worst_status(statuses)
    avg_load = (total_load / load_count) if load_count > 0 else 0.0
    avg_battery_charge = (total_battery_charge / battery_count) if battery_count > 0 else 0.0
    avg_input_voltage = (total_input_voltage / input_voltage_count) if input_voltage_count > 0 else 0.0
    avg_output_voltage = (total_output_voltage / output_voltage_count) if output_voltage_count > 0 else 0.0

    aggregated = {
        # Combined status (worst case)
        'ups_status': worst_status,
        'ups.status': worst_status,  # Include both formats for compatibility

        # Total power
        'ups_realpower': round(total_realpower, 2),
        'ups.realpower': round(total_realpower, 2),

        # Average load
        'ups_load': round(avg_load, 1),
        'ups.load': round(avg_load, 1),

        # Average battery charge
        'battery_charge': round(avg_battery_charge, 1),
        'battery.charge': round(avg_battery_charge, 1),

        # Minimum runtime
        'battery_runtime': round(min_runtime, 0) if min_runtime is not None else 0,
        'battery.runtime': round(min_runtime, 0) if min_runtime is not None else 0,

        # Average voltages
        'input_voltage': round(avg_input_voltage, 1),
        'input.voltage': round(avg_input_voltage, 1),
        'output_voltage': round(avg_output_voltage, 1),
        'output.voltage': round(avg_output_voltage, 1),

        # Device counts
        'ups_count': ups_count,
        'ups_online_count': online_count,
        'ups_offline_count': ups_count - online_count,

        # Metadata
        'is_aggregated': True,
        'source': 'multi_ups_aggregation'
    }

    logger.debug(
        f"📊 Aggregated {ups_count} UPS: "
        f"status={worst_status}, power={total_realpower:.2f}W, "
        f"battery={avg_battery_charge:.1f}%, online={online_count}/{ups_count}"
    )

    return aggregated


def aggregate_ups_data_with_details(all_ups_data):
    """
    Aggregate UPS data with additional details about individual devices.

    Returns both aggregated metrics and per-device summaries.

    Args:
        all_ups_data: Dictionary of {ups_id: UPSData} or list of UPSData objects

    Returns:
        dict: {
            'aggregated': Aggregated metrics,
            'devices': List of device summaries
        }
    """
    # Get basic aggregation
    aggregated = aggregate_ups_data(all_ups_data)

    # Build device summaries
    devices = []

    # Convert to list if dict
    if isinstance(all_ups_data, dict):
        for ups_id, ups_data in all_ups_data.items():
            device_summary = {
                'ups_id': ups_id,
                'status': safe_get(ups_data, 'ups_status', safe_get(ups_data, 'ups.status', 'UNKNOWN')),
                'battery_charge': safe_float(safe_get(ups_data, 'battery_charge', safe_get(ups_data, 'battery.charge', 0))),
                'realpower': safe_float(safe_get(ups_data, 'ups_realpower', safe_get(ups_data, 'ups.realpower', 0))),
                'load': safe_float(safe_get(ups_data, 'ups_load', safe_get(ups_data, 'ups.load', 0))),
            }
            devices.append(device_summary)

    return {
        'aggregated': aggregated,
        'devices': devices
    }
