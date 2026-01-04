"""
Database migrations module for Nutify.

This module handles database schema migrations to support multi-UPS functionality
and other future schema changes.
"""

from .multi_ups_migration import run_multi_ups_migration, check_migration_needed

__all__ = ['run_multi_ups_migration', 'check_migration_needed']
