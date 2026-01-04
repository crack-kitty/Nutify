"""
UPS Data Cache Module.
This module provides a caching system for UPS data.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import threading
import json
from flask import current_app
import pytz

from core.logger import database_logger as logger
from core.db.ups import db
from core.db.ups.utils import data_lock
from core.db.ups.data import get_ups_data, get_all_ups_data
from core.db.ups.aggregator import aggregate_ups_data
from flask_socketio import SocketIO

# Lock for cache operations
data_lock = threading.Lock()

# WebSocket instance for cache updates
websocket = SocketIO()

class UPSDataCache:
    """
    UPS data caching system for efficient data storage and aggregation.
    
    This class provides:
    - Buffering of UPS data points
    - Calculation of averages and aggregates
    - Automatic saving with proper time alignment
    - Hourly and daily aggregations
    - Real-time WebSocket updates to clients
    """
    
    def __init__(self, size=5):
        """
        Initialize the cache with Pandas

        Args:
            size (int): Size of the buffer in seconds
        """
        self.size = size
        self.data = []  # Legacy single-UPS buffer (for backward compatibility)
        self.df = None

        # Multi-UPS data tracking
        self.per_ups_data = {}  # {ups_id: [(timestamp, data_dict), ...]}
        self.per_ups_df = {}    # {ups_id: DataFrame}
        self.aggregated_data = []  # Buffer for aggregated data
        self.aggregated_df = None

        self.next_save_time = None
        self.next_hour = None  #  For tracking the next hour
        self.hourly_data = []  # Buffer for hourly data
        self.last_daily_aggregation = None

        # Last broadcasted cache data
        self.last_broadcast = None
        self.last_broadcast_aggregated = None  # Aggregated data
        self.last_broadcast_per_ups = {}       # Per-UPS data

        cache_seconds = 60  # Fixed value
        logger.info(f"📊 Initialized UPS data cache (size: {size} seconds, cache seconds: {cache_seconds}, multi-UPS support enabled)")

    def get_next_hour(self, current_time):
        """
        Calculate the exact next hour in UTC for database storage
        
        Args:
            current_time: Current timestamp
            
        Returns:
            datetime: Next hour timestamp in UTC
        """
        # Create a UTC timestamp directly
        utc_time = datetime.now(pytz.UTC)
        
        # Calculate the exact next hour in UTC
        next_hour_utc = utc_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        
        logger.debug(f"Next hour calculated in UTC: {next_hour_utc}")
        return next_hour_utc

    def calculate_hourly_average(self):
        """
        Calculate the hourly average of ups_realpower
        
        Returns:
            float: Hourly average or None if no data
        """
        if not self.hourly_data:
            return None
            
        df = pd.DataFrame(self.hourly_data)
        if 'ups_realpower' not in df.columns:
            return None
            
        return round(df['ups_realpower'].mean(), 2)

    def calculate_and_save_averages(self, db, UPSDynamicData, current_time):
        """
        Calculate averages and save to database if needed
        
        Args:
            db: Database instance
            UPSDynamicData: UPS dynamic data model class
            current_time: Current timestamp (not used, we use UTC directly)
            
        Returns:
            bool: True if data was saved, False otherwise
        """
        try:
            # Get current time in UTC for consistency
            utc_now = datetime.now(pytz.UTC)
            
            # Initialize next_hour if necessary
            if self.next_hour is None:
                self.next_hour = self.get_next_hour(utc_now)

            # Check if it's time to save the normal data
            if not self.is_save_time(utc_now):
                return False

            # Calculate averages using the existing code
            averages = self.calculate_averages()
            if not averages:
                return False

            logger.info(f"📊 Processing averages from {len(self.data)} samples at {self.next_save_time} UTC")

            # Create a new record
            dynamic_data = UPSDynamicData()

            # Set timestamp_utc - already in UTC
            dynamic_data.timestamp_utc = self.next_save_time
            logger.info(f"⏰ Setting timestamp_utc to {self.next_save_time} UTC")

            # Check critical fields before setting values
            critical_fields = ['ups_status', 'ups_load', 'ups_realpower', 'ups_realpower_nominal']
            for field in critical_fields:
                if field in averages:
                    logger.info(f"Critical field {field} = {averages[field]} in averages")
                else:
                    logger.warning(f"Critical field {field} missing from averages")

            # Set the average values
            missing_keys = []
            for key, value in averages.items():
                if hasattr(dynamic_data, key):
                    setattr(dynamic_data, key, value)
                    if key in critical_fields:
                        logger.info(f"✅ Set critical field {key}={value} on UPSDynamicData")
                    else:
                        logger.debug(f"✅ Set {key}={value} on UPSDynamicData")
                else:
                    missing_keys.append(key)
                    logger.warning(f"⚠️ Key {key} not found in UPSDynamicData model")
            
            if missing_keys:
                logger.warning(f"⚠️ {len(missing_keys)} keys from averages were not in the model: {missing_keys[:5]}...")
                
            # Double-check critical fields after setting them
            for field in critical_fields:
                if hasattr(dynamic_data, field):
                    value = getattr(dynamic_data, field)
                    if value is None:
                        logger.warning(f"⚠️ Critical field '{field}' is None after setting")
                        if field in averages:
                            setattr(dynamic_data, field, averages[field])
                            logger.info(f"Fixed {field} to {averages[field]}")
                    else:
                        logger.info(f"Verified {field} = {value} on UPSDynamicData")
                else:
                    logger.warning(f"⚠️ Critical field '{field}' not found in UPSDynamicData model")

            # Add to hourly buffer if ups_realpower is present
            if 'ups_realpower' in averages:
                self.hourly_data.append({
                    'timestamp': self.next_save_time,  # Already in UTC
                    'ups_realpower': averages['ups_realpower']
                })

                # Check if it's time to calculate the hourly average
                if utc_now >= self.next_hour:
                    exact_hour = self.next_hour - timedelta(hours=1)  # Both in UTC
                    
                    logger.info(f"Calculating hourly average for hour ending at {self.next_hour} UTC")

                    # Query for records in UTC timeframe
                    hour_data = UPSDynamicData.query.filter(
                        UPSDynamicData.timestamp_utc >= exact_hour,
                        UPSDynamicData.timestamp_utc < self.next_hour
                    ).all()

                    if hour_data:
                        powers = [d.ups_realpower for d in hour_data if d.ups_realpower is not None]
                        if powers:
                            hourly_avg = sum(powers) / len(powers)
                            dynamic_data.ups_realpower_hrs = round(hourly_avg, 2)
                            logger.info(f"📊 Calculated hourly average from {len(powers)} records: {hourly_avg}W. Saving ups_realpower_hrs = {dynamic_data.ups_realpower_hrs}")
                        else:
                            logger.warning("📊 No power data available for hourly average calculation.")
                    else:
                        logger.warning("📊 No hourly data found in database for hourly average calculation.")

                    # Reset for the next hour
                    self.hourly_data = []
                    self.next_hour = self.get_next_hour(utc_now)
                    logger.info(f"Next hourly calculation at: {self.next_hour} UTC")
                else:
                    logger.debug("⏰ Not yet time for hourly calculation.")

            # Save in the database
            with data_lock:
                db.session.add(dynamic_data)
                db.session.commit()
                logger.info(f"💾 Successfully saved averaged data at {self.next_save_time} UTC")

            # Clean the buffer and update next_save_time
            self.data = []
            self.df = None
            self.next_save_time = self.get_next_minute(utc_now)
            logger.info(f"Next save scheduled for: {self.next_save_time} UTC")

            if self.should_aggregate_daily(utc_now):
                self.aggregate_daily_data(db, UPSDynamicData, utc_now)

            return True

        except Exception as e:
            logger.error(f"❌ Error saving averaged data: {str(e)}", exc_info=True)
            return False

    def get_next_minute(self, current_time):
        """
        Calculate the exact next minute in UTC for database storage
        
        Args:
            current_time (datetime): Current timestamp
        
        Returns:
            datetime: Exact next minute timestamp in UTC
        """
        # Create a UTC timestamp directly
        utc_time = datetime.now(pytz.UTC)
        
        # Calculate the exact next minute in UTC
        next_minute_utc = utc_time.replace(second=0, microsecond=0) + timedelta(minutes=1)
        
        logger.debug(f"Next save time calculated in UTC: {next_minute_utc}")
        return next_minute_utc

    def add(self, timestamp, data):
        """
        Add data to the buffer and initialize next_save_time if necessary
        
        Args:
            timestamp (datetime): Data timestamp
            data (dict): UPS data dictionary
        """
        # If it's the first data point, initialize next_save_time
        if self.next_save_time is None:
            self.next_save_time = self.get_next_minute(timestamp)
            logger.info(f"First data point received. Next save scheduled for: {self.next_save_time}")

        # Ensure keys are in the correct format (with underscores instead of dots)
        formatted_data = {}
        for key, value in data.items():
            # Convert key from dot notation to underscore if needed
            formatted_key = key.replace('.', '_')
            formatted_data[formatted_key] = value

        # Log the transformation if it occurred
        if len(formatted_data) != len(data):
            logger.info(f"Transformed {len(data)} keys to {len(formatted_data)} formatted keys")
        elif any(key != formatted_key for key, formatted_key in zip(data.keys(), formatted_data.keys())):
            logger.info("Some keys were transformed from dots to underscores")

        # Add to the buffer
        self.data.append((timestamp, formatted_data))
        
        # Convert the buffer to DataFrame
        df_data = []
        for ts, d in self.data:
            row = {'timestamp': ts, **d}
            df_data.append(row)
        
        self.df = pd.DataFrame(df_data)
        logger.debug(f"📥 Added data point (buffer: {len(self.data)})")
        
        # Broadcast cache update to clients via WebSocket
        self.broadcast_cache_update(formatted_data)

    def add_multi_ups(self, timestamp, all_ups_data):
        """
        Add data from multiple UPS devices to the buffer.

        Args:
            timestamp (datetime): Data timestamp
            all_ups_data (dict): Dictionary of {ups_id: UPSData}
        """
        # If it's the first data point, initialize next_save_time
        if self.next_save_time is None:
            self.next_save_time = self.get_next_minute(timestamp)
            logger.info(f"First multi-UPS data received. Next save scheduled for: {self.next_save_time}")

        # Process each UPS device
        for ups_id, ups_data in all_ups_data.items():
            # Ensure keys are in the correct format
            formatted_data = {}
            data_dict = vars(ups_data) if hasattr(ups_data, '__dict__') else ups_data

            for key, value in data_dict.items():
                # Convert key from dot notation to underscore if needed
                formatted_key = key.replace('.', '_')
                formatted_data[formatted_key] = value

            # Initialize buffer for this UPS if needed
            if ups_id not in self.per_ups_data:
                self.per_ups_data[ups_id] = []

            # Add to the UPS-specific buffer
            self.per_ups_data[ups_id].append((timestamp, formatted_data))

            # Convert to DataFrame for this UPS
            df_data = []
            for ts, d in self.per_ups_data[ups_id]:
                row = {'timestamp': ts, **d}
                df_data.append(row)

            self.per_ups_df[ups_id] = pd.DataFrame(df_data)

        # Calculate and store aggregated data
        aggregated = aggregate_ups_data(all_ups_data)

        # Add aggregated data to buffer
        self.aggregated_data.append((timestamp, aggregated))

        # Convert aggregated buffer to DataFrame
        agg_df_data = []
        for ts, d in self.aggregated_data:
            row = {'timestamp': ts, **d}
            agg_df_data.append(row)

        self.aggregated_df = pd.DataFrame(agg_df_data)

        logger.debug(
            f"📥 Added multi-UPS data: {len(all_ups_data)} UPS devices, "
            f"aggregated buffer: {len(self.aggregated_data)}"
        )

        # Broadcast multi-UPS cache update
        self.broadcast_multi_ups_update(aggregated, all_ups_data)

    def is_save_time(self, current_time):
        """
        Check if it's time to save the data
        
        Args:
            current_time: Current timestamp
            
        Returns:
            bool: True if it's time to save, False otherwise
        """
        # If next_save_time is not set, it's not time to save
        if self.next_save_time is None:
            return False
            
        # Get current time in UTC for comparison
        current_utc = datetime.now(pytz.UTC)
            
        # Check if current time is beyond next_save_time
        if current_utc >= self.next_save_time:
            logger.debug(f"⏰ Time to save! Current UTC: {current_utc}, Save time: {self.next_save_time}")
            return True
        else:
            return False

    def calculate_averages(self):
        """
        Calculate averages using Pandas:
        - Automatically identifies numeric columns
        - Calculates average for numeric values
        - Takes last value for non-numeric columns
        
        Returns:
            dict: Dictionary with averages and last values
        """
        if self.df is None or self.df.empty:
            logger.warning("⚠️ No data available for averaging")
            return None

        try:
            logger.info("📊 Starting Pandas data processing...")
            
            # Log all columns for debugging
            logger.debug(f"Available columns: {list(self.df.columns)}")
            
            # Check if ups_realpower exists in the data
            if 'ups_realpower' in self.df.columns:
                logger.info(f"ups_realpower values in buffer: {list(self.df['ups_realpower'].values)}")
            else:
                logger.warning("ups_realpower not found in data columns!")
            
            # Identify numeric columns
            numeric_cols = self.df.select_dtypes(include=[np.number]).columns
            non_numeric_cols = self.df.select_dtypes(exclude=[np.number]).columns
            non_numeric_cols = non_numeric_cols.drop('timestamp') if 'timestamp' in non_numeric_cols else non_numeric_cols

            logger.debug(f"🔢 Processing {len(numeric_cols)} numeric columns with Pandas")
            # Calculate averages for numeric columns (rounded to 2 decimal places)
            averages = self.df[numeric_cols].mean().round(2).to_dict()

            logger.debug(f"📝 Processing {len(non_numeric_cols)} non-numeric columns")
            # Take last value for non-numeric columns
            last_values = self.df[non_numeric_cols].iloc[-1].to_dict()

            # Combine results
            result = {**averages, **last_values}
            
            # Log important calculated values
            logger.info(f"Calculated averages: ups_load={result.get('ups_load', 'N/A')}%, ups_realpower={result.get('ups_realpower', 'N/A')}W")
            
            logger.info(f"✅ Pandas processing complete - averaged {len(numeric_cols)} numeric fields")
            return result

        except Exception as e:
            logger.error(f"❌ Error in Pandas processing: {str(e)}")
            return None

    def is_full(self):
        """
        Check if the buffer is full
        
        Returns:
            bool: True if buffer is full
        """
        return len(self.data) >= self.size

    def should_aggregate_daily(self, current_time):
        """
        Check if it's time for daily aggregation (4AM UTC)
        
        Args:
            current_time: Current timestamp (not used as we get fresh UTC time)
            
        Returns:
            bool: True if it's time to aggregate daily data, False otherwise
        """
        # Get current time in UTC
        now_utc = datetime.now(pytz.UTC)
        
        # If it's the first time, initialize last_daily_aggregation
        if self.last_daily_aggregation is None:
            # Initialize to today at 4 AM UTC
            day_start = now_utc.replace(hour=4, minute=0, second=0, microsecond=0)
            
            # If current time is after 4 AM, set to tomorrow
            if now_utc.hour >= 4:
                day_start = day_start + timedelta(days=1)
                
            self.last_daily_aggregation = day_start
            logger.info(f"📅 Initialized daily aggregation time to {day_start} UTC")
            return False
        
        # Check if it's past the scheduled aggregation time (4 AM UTC)
        if now_utc >= self.last_daily_aggregation:
            logger.info(f"📅 Time for daily aggregation: {now_utc} UTC")
            # Update for next day
            self.last_daily_aggregation = self.last_daily_aggregation + timedelta(days=1)
            return True
            
        return False

    def aggregate_daily_data(self, db, UPSDynamicData, current_time):
        """
        Perform daily aggregation
        
        Args:
            db: Database instance
            UPSDynamicData: UPS dynamic data model class
            current_time: Current timestamp (not used, we use UTC directly)
        """
        try:
            # Use UTC for database operations
            now_utc = datetime.now(pytz.UTC)
            # Set to midnight of current day in UTC
            aggregation_time = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
            logger.debug(f"📅 Starting daily aggregation at: {aggregation_time} UTC")

            # Calculate the average of hourly averages
            logger.debug("📅 Querying hourly averages for daily aggregation...")
            from sqlalchemy import func
            daily_data = db.session.query(
                func.avg(UPSDynamicData.ups_realpower_hrs).label('daily_avg')
            ).filter(
                UPSDynamicData.timestamp_utc >= aggregation_time - timedelta(days=1),
                UPSDynamicData.timestamp_utc < aggregation_time
            ).scalar()

            if daily_data:
                daily_avg = round(float(daily_data), 2)
                logger.debug(f"📅 Daily average power calculated: {daily_avg}W")

                # Create entry with previous day as timestamp (UTC)
                new_daily = UPSDynamicData(
                    timestamp_utc=aggregation_time - timedelta(days=1),
                    ups_realpower_days=daily_avg
                )

                with data_lock:
                    db.session.add(new_daily)
                    db.session.commit()
                    logger.info(f"📅 Daily aggregation saved: {daily_avg}W for {aggregation_time.date()} UTC")
            else:
                logger.warning("📅 No hourly data found for daily aggregation.")

        except Exception as e:
            logger.error(f"❌ Daily aggregation error: {str(e)}", exc_info=True)
            db.session.rollback()

    def get(self):
        """
        Return the current data stored in cache.
        
        Returns:
            list: List of data points in the cache
        """
        return self.data
        
    def broadcast_cache_update(self, data):
        """
        Broadcast cache update to all connected WebSocket clients
        
        Args:
            data (dict): The new data to be broadcasted
        """
        try:
            # Only send if there's meaningful data
            if not data:
                return
            
            # Create a timestamp for the broadcast
            broadcast_data = {
                'timestamp': datetime.now().isoformat(),
                **data  # Include all data fields from the cache
            }
            
            # Check if data changed meaningfully from last broadcast to avoid unnecessary broadcasts
            if self.last_broadcast:
                # Check status change (always broadcast if status changes)
                status_changed = broadcast_data.get('ups_status') != self.last_broadcast.get('ups_status')
                
                # Check for significant numeric changes
                significant_change = False
                important_metrics = ['ups_load', 'battery_charge', 'ups_realpower', 'input_voltage']
                for metric in important_metrics:
                    if metric in broadcast_data and metric in self.last_broadcast:
                        try:
                            current_val = float(broadcast_data[metric] or 0)
                            last_val = float(self.last_broadcast[metric] or 0)
                            if abs(current_val - last_val) >= 1.0:  # 1% or 1W threshold
                                significant_change = True
                                break
                        except (ValueError, TypeError):
                            # If values can't be compared, assume there's a change
                            significant_change = True
                            break
                
                # Skip broadcast if no meaningful changes
                if not status_changed and not significant_change:
                    logger.debug("🔄 Skipping WebSocket broadcast - no significant changes")
                    return
            
            # Update last broadcast
            self.last_broadcast = broadcast_data.copy()
            
            # Broadcast the data
            logger.debug(f"📡 Broadcasting cache update with {len(broadcast_data)} fields")
            websocket.emit('cache_update', broadcast_data)
            
        except Exception as e:
            logger.error(f"❌ Error broadcasting cache update: {str(e)}")
    
    def get_latest_cache_data(self):
        """
        Get the latest cache data for new WebSocket connections

        Returns:
            dict: Latest cache data or empty dict if no data
        """
        if not self.last_broadcast:
            return {}
        return self.last_broadcast

    def broadcast_multi_ups_update(self, aggregated_data, per_ups_data):
        """
        Broadcast multi-UPS cache update to all connected WebSocket clients.

        Args:
            aggregated_data (dict): Aggregated metrics across all UPS
            per_ups_data (dict): Dictionary of {ups_id: UPSData}
        """
        try:
            if not aggregated_data:
                return

            # Create timestamp for broadcast
            timestamp = datetime.now().isoformat()

            # Prepare aggregated data for broadcast
            broadcast_aggregated = {
                'timestamp': timestamp,
                **aggregated_data
            }

            # Prepare per-UPS data for broadcast
            broadcast_per_ups = {}
            for ups_id, ups_data in per_ups_data.items():
                data_dict = vars(ups_data) if hasattr(ups_data, '__dict__') else ups_data
                broadcast_per_ups[ups_id] = {
                    'timestamp': timestamp,
                    **data_dict
                }

            # Check for significant changes
            should_broadcast = False

            # Check aggregated status change
            if (self.last_broadcast_aggregated is None or
                broadcast_aggregated.get('ups_status') != self.last_broadcast_aggregated.get('ups_status')):
                should_broadcast = True

            # Check for significant numeric changes in aggregated data
            if not should_broadcast and self.last_broadcast_aggregated:
                important_metrics = ['ups_load', 'battery_charge', 'ups_realpower', 'input_voltage']
                for metric in important_metrics:
                    if metric in broadcast_aggregated and metric in self.last_broadcast_aggregated:
                        try:
                            current_val = float(broadcast_aggregated[metric] or 0)
                            last_val = float(self.last_broadcast_aggregated[metric] or 0)
                            if abs(current_val - last_val) >= 1.0:
                                should_broadcast = True
                                break
                        except (ValueError, TypeError):
                            should_broadcast = True
                            break

            # Skip broadcast if no meaningful changes
            if not should_broadcast:
                logger.debug("🔄 Skipping multi-UPS WebSocket broadcast - no significant changes")
                return

            # Update last broadcast
            self.last_broadcast_aggregated = broadcast_aggregated.copy()
            self.last_broadcast_per_ups = broadcast_per_ups.copy()

            # Broadcast the multi-UPS data
            multi_ups_broadcast = {
                'aggregated': broadcast_aggregated,
                'individual': broadcast_per_ups,
                'ups_count': len(per_ups_data)
            }

            logger.debug(
                f"📡 Broadcasting multi-UPS update: {len(per_ups_data)} devices, "
                f"aggregated status={broadcast_aggregated.get('ups_status', 'UNKNOWN')}"
            )
            websocket.emit('multi_ups_update', multi_ups_broadcast)

        except Exception as e:
            logger.error(f"❌ Error broadcasting multi-UPS update: {str(e)}")

    def get_latest_multi_ups_data(self):
        """
        Get the latest multi-UPS cache data for new WebSocket connections.

        Returns:
            dict: Latest multi-UPS data with aggregated and individual metrics
        """
        if not self.last_broadcast_aggregated:
            return {}

        return {
            'aggregated': self.last_broadcast_aggregated,
            'individual': self.last_broadcast_per_ups,
            'ups_count': len(self.last_broadcast_per_ups)
        }

def save_ups_data(db, UPSDynamicData, ups_data_cache):
    """
    Get the current UPS data and save it to the cache.
    Supports both single-UPS and multi-UPS modes.

    Args:
        db: Database instance
        UPSDynamicData: UPS dynamic data model class
        ups_data_cache: UPS data cache instance

    Returns:
        tuple: (success, error_message)
    """
    try:
        # Check for multi-UPS mode by checking if ups_devices table has entries
        from core.db.ups.utils import ups_config_manager

        # Try to load UPS devices from database
        ups_config_manager.ensure_initialized()
        enabled_devices = ups_config_manager.get_all_enabled()

        # Use UTC time directly for database operations
        now_utc = datetime.now(pytz.UTC)

        # Get polling interval from VariableConfig
        try:
            if hasattr(db, 'ModelClasses') and hasattr(db.ModelClasses, 'VariableConfig'):
                model_class = db.ModelClasses.VariableConfig
            else:
                from core.db.ups import VariableConfig
                model_class = VariableConfig

            config = model_class.query.first()
            polling_interval = config.polling_interval if config else 1
        except Exception as e:
            logger.error(f"Error getting polling interval: {str(e)}. Using default of 1 second.")
            polling_interval = 1

        # Adjust cache size based on polling interval
        if polling_interval > 1:
            cache_seconds = 60  # Fixed value
            target_buffer_size = max(5, int(cache_seconds / polling_interval))
            if ups_data_cache.size != target_buffer_size:
                logger.info(
                    f"Adjusting cache buffer size from {ups_data_cache.size} to {target_buffer_size} "
                    f"based on polling interval of {polling_interval} seconds"
                )
                ups_data_cache.size = target_buffer_size

        # Multi-UPS mode: multiple devices configured
        if len(enabled_devices) > 1:
            logger.debug(f"📊 Multi-UPS mode: polling {len(enabled_devices)} devices")

            # Get data from all UPS devices
            all_ups_data = get_all_ups_data()

            if not all_ups_data:
                error_msg = "No UPS data retrieved from any device"
                logger.warning(f"⚠️ {error_msg}")
                return False, error_msg

            # Add multi-UPS data to cache
            ups_data_cache.add_multi_ups(now_utc, all_ups_data)

            # Check if it's time to save (using aggregated data)
            # TODO: Implement multi-UPS save logic
            logger.debug(f"📥 Multi-UPS buffer status: aggregated={len(ups_data_cache.aggregated_data)}")

            return True, None

        # Single-UPS mode: backward compatibility
        else:
            logger.debug("📊 Single-UPS mode (backward compatibility)")

            # Check connection status first
            from core.db.internal_checker import is_ups_connected

            if not is_ups_connected():
                error_msg = "UPS connection unavailable, skipping data collection"
                logger.warning(f"⚠️ {error_msg}")
                return False, error_msg

            # Get data from single UPS
            data = get_ups_data()

            # Convert DotDict to standard dictionary
            data_dict = vars(data)

            # Log the buffer
            logger.debug(f"📥 Buffer status before add: {len(ups_data_cache.data)}")
            ups_data_cache.add(now_utc, data_dict)
            logger.debug(f"📥 Buffer status after add: {len(ups_data_cache.data)}")

            # Check if it's time to save
            success = ups_data_cache.calculate_and_save_averages(db, UPSDynamicData, now_utc)
            if success:
                logger.info("💾 Successfully saved aligned data to database")

            return True, None

    except Exception as e:
        error_msg = f"Error saving data: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return False, error_msg

# Initialize the global cache
cache_seconds = 60  # Fixed value
ups_data_cache = UPSDataCache(size=cache_seconds)  # Initial size, will be adjusted based on polling interval

# WebSocket event handlers
@websocket.on('connect')
def handle_websocket_connect():
    """Handle new WebSocket connection and send latest data"""
    from flask import request
    logger.info(f"🟢 WebSocket client connected - SID: {request.sid}")
    # Send initial data to the client
    latest_data = ups_data_cache.get_latest_cache_data()
    if latest_data:
        websocket.emit('cache_update', latest_data, room=request.sid)

@websocket.on('request_cache_data')
def handle_request_cache_data():
    """Handle request for latest cache data"""
    from flask import request
    logger.debug(f"📤 Client {request.sid} requested cache data")
    latest_data = ups_data_cache.get_latest_cache_data()
    websocket.emit('cache_update', latest_data, room=request.sid)

@websocket.on('disconnect')
def handle_websocket_disconnect():
    """Handle WebSocket disconnection"""
    from flask import request
    logger.info(f"🔴 WebSocket client disconnected - SID: {request.sid}")

def init_websocket(app):
    """Initialize WebSocket with Flask app"""
    logger.info("🔌 Initializing UPS Cache WebSocket")
    websocket.init_app(app, cors_allowed_origins="*", async_mode='eventlet')
    return websocket 