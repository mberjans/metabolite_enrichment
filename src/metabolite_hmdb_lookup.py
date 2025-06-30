"""
Core HMDB ID lookup functions for metabolite matching.

This module provides fundamental functions for converting between metabolite names
and HMDB IDs, and retrieving metabolite information from various data sources.

Functions:
    - get_hmdb_id_from_name: Convert metabolite name to HMDB ID
    - get_metabolite_name_from_hmdb_id: Convert HMDB ID to metabolite name
    - get_metabolite_info_by_hmdb_id: Get metabolite info from CSV by HMDB ID
    - get_diet_advice_by_hmdb_id: Get diet advice by HMDB ID and status
    - is_valid_hmdb_id: Validate HMDB ID format
"""

import pandas as pd
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

import logging

# Import timeout handling
from timeout_handler import load_csv_safe, load_json_safe, TimeoutError

# Set up logging
logger = logging.getLogger(__name__)

# Global cache for loaded data
_data_cache = {}

def is_valid_hmdb_id(hmdb_id: str) -> bool:
    """
    Validate HMDB ID format.

    Args:
        hmdb_id (str): HMDB ID to validate

    Returns:
        bool: True if valid HMDB ID format (HMDB followed by 7 digits)
    """
    if not isinstance(hmdb_id, str):
        return False

    # HMDB ID format: HMDB followed by 7 digits
    pattern = r'^HMDB\d{7}$'
    return bool(re.match(pattern, hmdb_id))


def _load_normal_ranges_csv(csv_path: str = "input/normal_ranges.csv") -> pd.DataFrame:
    """
    Load normal ranges CSV file with caching.

    Args:
        csv_path (str): Path to normal ranges CSV file

    Returns:
        pd.DataFrame: Normal ranges dataframe

    Raises:
        FileNotFoundError: If CSV file doesn't exist
        Exception: If CSV file cannot be loaded
    """
    cache_key = f"normal_ranges_{csv_path}"

    if cache_key in _data_cache:
        return _data_cache[cache_key]

    try:
        if not Path(csv_path).exists():
            raise FileNotFoundError(f"Normal ranges CSV file not found: {csv_path}")

        # Use timeout-protected CSV loading
        df = load_csv_safe(csv_path)

        if df is None:
            raise TimeoutError(f"Failed to load CSV file (timeout or error): {csv_path}")

        # Validate required columns
        required_columns = ['chemical_name', 'hmdb']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns in CSV: {missing_columns}")

        # Cache the dataframe
        _data_cache[cache_key] = df
        logger.info(f"Loaded normal ranges CSV with {len(df)} entries from {csv_path}")

        return df

    except Exception as e:
        logger.error(f"Error loading normal ranges CSV from {csv_path}: {e}")
        raise


def _load_diet_advice_json(json_path: str) -> Dict[str, Any]:
    """
    Load diet advice JSON file with caching.

    Args:
        json_path (str): Path to diet advice JSON file

    Returns:
        Dict[str, Any]: Diet advice data keyed by HMDB ID
    """
    cache_key = f"diet_advice_{json_path}"

    if cache_key in _data_cache:
        return _data_cache[cache_key]

    try:
        if not Path(json_path).exists():
            logger.warning(f"Diet advice JSON file not found: {json_path}")
            return {}

        # Use timeout-protected JSON loading
        data = load_json_safe(json_path)

        if data is None:
            logger.warning(f"Failed to load JSON file (timeout or error): {json_path}")
            return {}

        # Cache the data
        _data_cache[cache_key] = data
        logger.info(f"Loaded diet advice JSON with {len(data)} entries from {json_path}")

        return data

    except Exception as e:
        logger.error(f"Error loading diet advice JSON from {json_path}: {e}")
        return {}


def get_hmdb_id_from_name(metabolite_name: str, csv_path: str = "input/normal_ranges.csv") -> Optional[str]:
    """
    Convert metabolite name to HMDB ID.

    Args:
        metabolite_name (str): Name of the metabolite
        csv_path (str): Path to normal ranges CSV file

    Returns:
        Optional[str]: HMDB ID if found, None otherwise
    """
    if not isinstance(metabolite_name, str) or not metabolite_name.strip():
        logger.warning("Invalid metabolite name provided")
        return None

    try:
        df = _load_normal_ranges_csv(csv_path)

        # Case-insensitive exact match first
        metabolite_name_lower = metabolite_name.strip().lower()
        df_lower = df['chemical_name'].str.lower()

        matches = df[df_lower == metabolite_name_lower]

        if not matches.empty:
            hmdb_id = matches.iloc[0]['hmdb']

            # Validate the HMDB ID format
            if is_valid_hmdb_id(hmdb_id):
                logger.debug(f"Found HMDB ID {hmdb_id} for metabolite '{metabolite_name}'")
                return hmdb_id
            else:
                logger.warning(f"Invalid HMDB ID format found for '{metabolite_name}': {hmdb_id}")
                return None

        logger.debug(f"No HMDB ID found for metabolite '{metabolite_name}'")
        return None

    except Exception as e:
        logger.error(f"Error looking up HMDB ID for '{metabolite_name}': {e}")
        return None


def get_metabolite_name_from_hmdb_id(hmdb_id: str, csv_path: str = "input/normal_ranges.csv") -> Optional[str]:
    """
    Convert HMDB ID to metabolite name.

    Args:
        hmdb_id (str): HMDB ID
        csv_path (str): Path to normal ranges CSV file

    Returns:
        Optional[str]: Metabolite name if found, None otherwise
    """
    if not is_valid_hmdb_id(hmdb_id):
        logger.warning(f"Invalid HMDB ID format: {hmdb_id}")
        return None

    try:
        df = _load_normal_ranges_csv(csv_path)

        matches = df[df['hmdb'] == hmdb_id]

        if not matches.empty:
            metabolite_name = matches.iloc[0]['chemical_name']
            logger.debug(f"Found metabolite name '{metabolite_name}' for HMDB ID {hmdb_id}")
            return metabolite_name

        logger.debug(f"No metabolite name found for HMDB ID {hmdb_id}")
        return None

    except Exception as e:
        logger.error(f"Error looking up metabolite name for HMDB ID {hmdb_id}: {e}")
        return None


def get_metabolite_info_by_hmdb_id(hmdb_id: str, csv_path: str = "input/normal_ranges.csv") -> Dict[str, Any]:
    """
    Get metabolite information by HMDB ID from CSV.

    Args:
        hmdb_id (str): HMDB ID
        csv_path (str): Path to normal ranges CSV file

    Returns:
        Dict[str, Any]: Metabolite information including name, ranges, etc.
    """
    if not is_valid_hmdb_id(hmdb_id):
        logger.warning(f"Invalid HMDB ID format: {hmdb_id}")
        return {}

    try:
        df = _load_normal_ranges_csv(csv_path)

        matches = df[df['hmdb'] == hmdb_id]

        if not matches.empty:
            row = matches.iloc[0]

            # Convert to dictionary and handle NaN values
            info = row.to_dict()

            # Replace NaN values with None for JSON serialization
            for key, value in info.items():
                if pd.isna(value):
                    info[key] = None

            logger.debug(f"Found metabolite info for HMDB ID {hmdb_id}")
            return info

        logger.debug(f"No metabolite info found for HMDB ID {hmdb_id}")
        return {}

    except Exception as e:
        logger.error(f"Error getting metabolite info for HMDB ID {hmdb_id}: {e}")
        return {}


def get_diet_advice_by_hmdb_id(hmdb_id: str, status: str) -> Dict[str, Any]:
    """
    Get diet advice by HMDB ID and concentration status.

    Args:
        hmdb_id (str): HMDB ID
        status (str): Concentration status ('high' or 'low')

    Returns:
        Dict[str, Any]: Diet advice data if found, empty dict otherwise
    """
    if not is_valid_hmdb_id(hmdb_id):
        logger.warning(f"Invalid HMDB ID format: {hmdb_id}")
        return {}

    if status not in ['high', 'low']:
        logger.warning(f"Invalid status '{status}'. Must be 'high' or 'low'")
        return {}

    try:
        # Determine the correct JSON file based on status
        json_path = f"input/metabolite_info_{status}.json"

        diet_data = _load_diet_advice_json(json_path)

        if hmdb_id in diet_data:
            logger.debug(f"Found diet advice for HMDB ID {hmdb_id} with status '{status}'")
            return diet_data[hmdb_id]

        logger.debug(f"No diet advice found for HMDB ID {hmdb_id} with status '{status}'")
        return {}

    except Exception as e:
        logger.error(f"Error getting diet advice for HMDB ID {hmdb_id} with status '{status}': {e}")
        return {}


def clear_cache():
    """Clear the data cache. Useful for testing or when data files are updated."""
    global _data_cache
    _data_cache.clear()
    logger.info("Data cache cleared")


# Batch lookup function for multiple HMDB IDs
def get_diet_advice_batch(hmdb_ids: List[str], status: str) -> Dict[str, Dict[str, Any]]:
    """
    Get diet advice for multiple HMDB IDs in batch.

    Args:
        hmdb_ids (List[str]): List of HMDB IDs
        status (str): Concentration status ('high' or 'low')

    Returns:
        Dict[str, Dict[str, Any]]: Diet advice data keyed by HMDB ID
    """
    if status not in ['high', 'low']:
        logger.warning(f"Invalid status '{status}'. Must be 'high' or 'low'")
        return {}

    try:
        # Load the diet advice data once
        json_path = f"input/metabolite_info_{status}.json"
        diet_data = _load_diet_advice_json(json_path)

        results = {}
        for hmdb_id in hmdb_ids:
            if is_valid_hmdb_id(hmdb_id) and hmdb_id in diet_data:
                results[hmdb_id] = diet_data[hmdb_id]

        logger.debug(f"Found diet advice for {len(results)} out of {len(hmdb_ids)} HMDB IDs with status '{status}'")
        return results

    except Exception as e:
        logger.error(f"Error getting batch diet advice with status '{status}': {e}")
        return {}
