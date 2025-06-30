"""
Universal Metabolite HMDB Matcher Class

This module provides a comprehensive MetaboliteHMDBMatcher class that unifies
metabolite identification across all data sources including CSV files, JSON files,
and synonyms data.

The class implements a singleton pattern for memory efficiency and provides
bidirectional mapping between metabolite names and HMDB IDs with support for
synonyms, aliases, and multiple name variations.
"""

import json
import pandas as pd
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Set
import logging
from collections import defaultdict

# Import our basic lookup functions
from metabolite_hmdb_lookup import (
    is_valid_hmdb_id,
    _load_normal_ranges_csv,
    _load_diet_advice_json
)

# Set up logging
logger = logging.getLogger(__name__)

class MetaboliteHMDBMatcher:
    """
    Universal metabolite matcher that provides unified HMDB ID-based identification
    across all data sources with support for synonyms and multiple name variations.

    This class implements a singleton pattern for memory efficiency and builds
    comprehensive bidirectional mappings between metabolite names and HMDB IDs.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Implement singleton pattern for memory efficiency."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(MetaboliteHMDBMatcher, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self,
                 normal_ranges_path: str = "input/normal_ranges.csv",
                 metabolite_info_high_path: str = "input/metabolite_info_high.json",
                 metabolite_info_low_path: str = "input/metabolite_info_low.json",
                 synonyms_path: str = "data/metabolite_synonyms_and_categories.json"):
        """
        Initialize the MetaboliteHMDBMatcher with data loading.

        Args:
            normal_ranges_path (str): Path to normal ranges CSV file
            metabolite_info_high_path (str): Path to high metabolite info JSON
            metabolite_info_low_path (str): Path to low metabolite info JSON
            synonyms_path (str): Path to synonyms and categories JSON
        """
        # Prevent re-initialization in singleton pattern
        if self._initialized:
            return

        self.normal_ranges_path = normal_ranges_path
        self.metabolite_info_high_path = metabolite_info_high_path
        self.metabolite_info_low_path = metabolite_info_low_path
        self.synonyms_path = synonyms_path

        # Initialize mapping dictionaries
        self.hmdb_to_names: Dict[str, Set[str]] = defaultdict(set)
        self.name_to_hmdb: Dict[str, str] = {}
        self.name_to_hmdb_normalized: Dict[str, str] = {}

        # Build the mappings from all data sources
        self._build_mapping()

        self._initialized = True
        logger.info(f"MetaboliteHMDBMatcher initialized with {len(self.hmdb_to_names)} HMDB IDs and {len(self.name_to_hmdb)} name mappings")

    def _build_mapping(self):
        """
        Build comprehensive mappings from all available data sources.

        This method loads data from:
        1. normal_ranges.csv - Primary metabolite names and HMDB IDs
        2. metabolite_info_high.json - High concentration diet advice data
        3. metabolite_info_low.json - Low concentration diet advice data
        4. metabolite_synonyms_and_categories.json - Synonyms and aliases
        """
        logger.info("Building comprehensive metabolite mappings...")

        # Load mappings from normal_ranges.csv
        self._load_normal_ranges_mappings()

        # Load mappings from diet advice JSON files
        self._load_diet_advice_mappings()

        # Load mappings from synonyms and categories
        self._load_synonyms_mappings()

        logger.info(f"Mapping complete: {len(self.hmdb_to_names)} HMDB IDs, {len(self.name_to_hmdb)} names")

    def _load_normal_ranges_mappings(self):
        """Load mappings from normal_ranges.csv."""
        try:
            df = _load_normal_ranges_csv(self.normal_ranges_path)

            for _, row in df.iterrows():
                hmdb_id = row['hmdb']
                metabolite_name = row['chemical_name']

                if is_valid_hmdb_id(hmdb_id) and metabolite_name:
                    self._add_mapping(hmdb_id, metabolite_name)

            logger.info(f"Loaded {len(df)} mappings from normal_ranges.csv")

        except Exception as e:
            logger.error(f"Error loading normal ranges mappings: {e}")

    def _load_diet_advice_mappings(self):
        """Load mappings from diet advice JSON files."""
        for file_path, file_type in [
            (self.metabolite_info_high_path, "high"),
            (self.metabolite_info_low_path, "low")
        ]:
            try:
                data = _load_diet_advice_json(file_path)

                for hmdb_id, info in data.items():
                    if is_valid_hmdb_id(hmdb_id) and 'metabolite' in info:
                        metabolite_name = info['metabolite']
                        if metabolite_name:
                            self._add_mapping(hmdb_id, metabolite_name)

                logger.info(f"Loaded {len(data)} mappings from {file_type} diet advice")

            except Exception as e:
                logger.error(f"Error loading {file_type} diet advice mappings: {e}")

    def _load_synonyms_mappings(self):
        """Load mappings from synonyms and categories JSON."""
        try:
            if not Path(self.synonyms_path).exists():
                logger.warning(f"Synonyms file not found: {self.synonyms_path}")
                return

            with open(self.synonyms_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            synonym_count = 0

            for metabolite_name, metabolite_data in data.items():
                # Add primary metabolite name
                hmdb_ids = metabolite_data.get('hmdb_ids', [])
                for hmdb_id in hmdb_ids:
                    if is_valid_hmdb_id(hmdb_id):
                        self._add_mapping(hmdb_id, metabolite_name)

                # Add consensus synonyms
                consensus = metabolite_data.get('consensus', {})
                consensus_synonyms = consensus.get('synonyms', [])
                for synonym in consensus_synonyms:
                    if synonym and synonym.strip():
                        for hmdb_id in hmdb_ids:
                            if is_valid_hmdb_id(hmdb_id):
                                self._add_mapping(hmdb_id, synonym.strip())
                                synonym_count += 1

                # Add comprehensive synonyms (if different from consensus)
                comprehensive = metabolite_data.get('comprehensive', {})
                comprehensive_synonyms = comprehensive.get('synonyms', [])
                for synonym in comprehensive_synonyms:
                    if synonym and synonym.strip() and synonym not in consensus_synonyms:
                        for hmdb_id in hmdb_ids:
                            if is_valid_hmdb_id(hmdb_id):
                                self._add_mapping(hmdb_id, synonym.strip())
                                synonym_count += 1

                # Add HMDB synonyms from individual HMDB data
                hmdb_data_list = metabolite_data.get('hmdb_data', [])
                for hmdb_data in hmdb_data_list:
                    hmdb_id = hmdb_data.get('hmdb_id')
                    if is_valid_hmdb_id(hmdb_id):
                        # Add HMDB synonyms
                        hmdb_sources = hmdb_data.get('sources', {}).get('HMDB', {})
                        hmdb_synonyms = hmdb_sources.get('synonyms', [])
                        for synonym in hmdb_synonyms:
                            if synonym and synonym.strip():
                                self._add_mapping(hmdb_id, synonym.strip())
                                synonym_count += 1

                        # Add common name and IUPAC name
                        common_name = hmdb_sources.get('common_name', '')
                        iupac_name = hmdb_sources.get('iupac_name', '')

                        if common_name and common_name.strip():
                            self._add_mapping(hmdb_id, common_name.strip())
                            synonym_count += 1

                        if iupac_name and iupac_name.strip():
                            self._add_mapping(hmdb_id, iupac_name.strip())
                            synonym_count += 1

            logger.info(f"Loaded {len(data)} metabolites with {synonym_count} synonyms from synonyms file")

        except Exception as e:
            logger.error(f"Error loading synonyms mappings: {e}")

    def _add_mapping(self, hmdb_id: str, name: str):
        """
        Add a mapping between HMDB ID and metabolite name.

        Args:
            hmdb_id (str): Valid HMDB ID
            name (str): Metabolite name or synonym
        """
        if not is_valid_hmdb_id(hmdb_id) or not name or not name.strip():
            return

        name = name.strip()
        normalized_name = self.normalize_lookup(name)

        # Add to hmdb_to_names mapping
        self.hmdb_to_names[hmdb_id].add(name)

        # Add to name_to_hmdb mapping (case-sensitive)
        if name not in self.name_to_hmdb:
            self.name_to_hmdb[name] = hmdb_id

        # Add to normalized mapping (case-insensitive)
        if normalized_name not in self.name_to_hmdb_normalized:
            self.name_to_hmdb_normalized[normalized_name] = hmdb_id

    def normalize_lookup(self, identifier: str) -> str:
        """
        Normalize an identifier for lookup purposes.

        Args:
            identifier (str): Metabolite name or identifier

        Returns:
            str: Normalized identifier (lowercase, stripped)
        """
        if not isinstance(identifier, str):
            return ""
        return identifier.strip().lower()

    def get_hmdb_id(self, metabolite_name: str) -> Optional[str]:
        """
        Get HMDB ID for a metabolite name with case-insensitive matching.

        Args:
            metabolite_name (str): Metabolite name to look up

        Returns:
            Optional[str]: HMDB ID if found, None otherwise
        """
        if not isinstance(metabolite_name, str) or not metabolite_name.strip():
            return None

        # Try exact case-sensitive match first
        if metabolite_name in self.name_to_hmdb:
            return self.name_to_hmdb[metabolite_name]

        # Try case-insensitive match
        normalized_name = self.normalize_lookup(metabolite_name)
        if normalized_name in self.name_to_hmdb_normalized:
            return self.name_to_hmdb_normalized[normalized_name]

        return None

    def get_hmdb_id_with_confidence(self, metabolite_name: str) -> Dict[str, Any]:
        """
        Get HMDB ID for a metabolite name with confidence scoring.

        Args:
            metabolite_name (str): Metabolite name to look up

        Returns:
            Dict[str, Any]: Dictionary containing HMDB ID, confidence score, and match details
        """
        if not isinstance(metabolite_name, str) or not metabolite_name.strip():
            return {
                'hmdb_id': None,
                'confidence': 0.0,
                'match_type': 'no_match',
                'matched_name': None,
                'all_names': []
            }

        metabolite_name = metabolite_name.strip()
        normalized_name = self.normalize_lookup(metabolite_name)

        # Try exact case-sensitive match first (highest confidence)
        if metabolite_name in self.name_to_hmdb:
            hmdb_id = self.name_to_hmdb[metabolite_name]
            all_names = self.get_all_names(hmdb_id)
            primary_name = self.get_primary_name(hmdb_id)

            # Determine if this is a primary name or synonym
            is_primary = (metabolite_name == primary_name)
            confidence = 1.0 if is_primary else 0.95
            match_type = 'exact_primary' if is_primary else 'exact_synonym'

            return {
                'hmdb_id': hmdb_id,
                'confidence': confidence,
                'match_type': match_type,
                'matched_name': metabolite_name,
                'all_names': all_names,
                'primary_name': primary_name
            }

        # Try case-insensitive match (medium confidence)
        if normalized_name in self.name_to_hmdb_normalized:
            hmdb_id = self.name_to_hmdb_normalized[normalized_name]
            all_names = self.get_all_names(hmdb_id)
            primary_name = self.get_primary_name(hmdb_id)

            # Find the actual matched name (case-insensitive)
            matched_name = None
            for name in all_names:
                if self.normalize_lookup(name) == normalized_name:
                    matched_name = name
                    break

            # Determine confidence based on match type
            is_primary = (self.normalize_lookup(primary_name) == normalized_name)
            confidence = 0.85 if is_primary else 0.75
            match_type = 'case_insensitive_primary' if is_primary else 'case_insensitive_synonym'

            return {
                'hmdb_id': hmdb_id,
                'confidence': confidence,
                'match_type': match_type,
                'matched_name': matched_name or metabolite_name,
                'all_names': all_names,
                'primary_name': primary_name
            }

        # No match found
        return {
            'hmdb_id': None,
            'confidence': 0.0,
            'match_type': 'no_match',
            'matched_name': None,
            'all_names': [],
            'primary_name': None
        }

    def get_all_names(self, hmdb_id: str) -> List[str]:
        """
        Get all known names (including synonyms) for an HMDB ID.

        Args:
            hmdb_id (str): HMDB ID to look up

        Returns:
            List[str]: List of all known names for the HMDB ID
        """
        if not is_valid_hmdb_id(hmdb_id):
            return []

        return list(self.hmdb_to_names.get(hmdb_id, set()))

    def get_primary_name(self, hmdb_id: str) -> Optional[str]:
        """
        Get the primary (first/canonical) name for an HMDB ID.

        Args:
            hmdb_id (str): HMDB ID to look up

        Returns:
            Optional[str]: Primary name if found, None otherwise
        """
        names = self.get_all_names(hmdb_id)
        return names[0] if names else None

    def is_valid_hmdb_id(self, hmdb_id: str) -> bool:
        """
        Validate HMDB ID format.

        Args:
            hmdb_id (str): HMDB ID to validate

        Returns:
            bool: True if valid HMDB ID format
        """
        return is_valid_hmdb_id(hmdb_id)

    def get_mapping_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the current mappings.

        Returns:
            Dict[str, Any]: Statistics about mappings
        """
        total_names = sum(len(names) for names in self.hmdb_to_names.values())

        return {
            'total_hmdb_ids': len(self.hmdb_to_names),
            'total_name_mappings': len(self.name_to_hmdb),
            'total_normalized_mappings': len(self.name_to_hmdb_normalized),
            'total_names_including_synonyms': total_names,
            'average_names_per_hmdb_id': total_names / len(self.hmdb_to_names) if self.hmdb_to_names else 0
        }

    def search_metabolites(self, query: str, limit: int = 10, include_confidence: bool = False) -> List[Dict[str, Any]]:
        """
        Search for metabolites by partial name matching with optional confidence scoring.

        Args:
            query (str): Search query
            limit (int): Maximum number of results to return
            include_confidence (bool): Whether to include confidence scores for matches

        Returns:
            List[Dict[str, Any]]: List of matching metabolites with HMDB IDs, names, and optional confidence
        """
        if not query or not query.strip():
            return []

        query_lower = query.strip().lower()
        results = []

        # Search through all name mappings
        for name, hmdb_id in self.name_to_hmdb.items():
            if query_lower in name.lower():
                all_names = self.get_all_names(hmdb_id)
                primary_name = all_names[0] if all_names else name

                result = {
                    'hmdb_id': hmdb_id,
                    'matched_name': name,
                    'all_names': all_names,
                    'primary_name': primary_name
                }

                # Add confidence scoring if requested
                if include_confidence:
                    confidence_data = self.get_hmdb_id_with_confidence(name)
                    result.update({
                        'confidence': confidence_data['confidence'],
                        'match_type': confidence_data['match_type']
                    })

                    # Calculate search relevance score
                    search_relevance = self._calculate_search_relevance(query_lower, name.lower())
                    result['search_relevance'] = search_relevance

                results.append(result)

                if len(results) >= limit:
                    break

        # Sort by confidence and relevance if confidence scoring is enabled
        if include_confidence:
            results.sort(key=lambda x: (x['confidence'], x['search_relevance']), reverse=True)

        return results

    def _calculate_search_relevance(self, query: str, name: str) -> float:
        """
        Calculate search relevance score for partial matches.

        Args:
            query (str): Search query (lowercase)
            name (str): Metabolite name (lowercase)

        Returns:
            float: Relevance score between 0.0 and 1.0
        """
        if not query or not name:
            return 0.0

        # Exact match gets highest score
        if query == name:
            return 1.0

        # Starts with query gets high score
        if name.startswith(query):
            return 0.9

        # Contains query as whole word gets medium-high score
        if f" {query} " in f" {name} ":
            return 0.8

        # Contains query as substring gets medium score
        if query in name:
            # Score based on how much of the name the query represents
            return 0.5 + (len(query) / len(name)) * 0.3

        return 0.0

    def get_best_matches(self, metabolite_name: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Get the best matches for a metabolite name with confidence scoring.

        This method combines exact matching and partial search to find the most likely matches.

        Args:
            metabolite_name (str): Metabolite name to match
            max_results (int): Maximum number of results to return

        Returns:
            List[Dict[str, Any]]: List of best matches sorted by confidence
        """
        if not isinstance(metabolite_name, str) or not metabolite_name.strip():
            return []

        results = []

        # First, try exact match with confidence
        exact_match = self.get_hmdb_id_with_confidence(metabolite_name)
        if exact_match['hmdb_id']:
            results.append(exact_match)

        # If no exact match or we want more options, do partial search
        if not exact_match['hmdb_id'] or max_results > 1:
            search_results = self.search_metabolites(
                metabolite_name,
                limit=max_results * 2,  # Get more to filter
                include_confidence=True
            )

            # Add search results that aren't already in results
            existing_hmdb_ids = {r['hmdb_id'] for r in results}
            for search_result in search_results:
                if search_result['hmdb_id'] not in existing_hmdb_ids:
                    # Adjust confidence for partial matches
                    search_result['confidence'] *= 0.7  # Reduce confidence for partial matches
                    search_result['match_type'] = f"partial_{search_result['match_type']}"
                    results.append(search_result)

                    if len(results) >= max_results:
                        break

        # Sort by confidence
        results.sort(key=lambda x: x['confidence'], reverse=True)

        return results[:max_results]

    def get_metabolite_info_enhanced(self, identifier: str) -> Dict[str, Any]:
        """
        Get comprehensive metabolite information including all names and HMDB ID.

        Args:
            identifier (str): Metabolite name or HMDB ID

        Returns:
            Dict[str, Any]: Comprehensive metabolite information
        """
        if not isinstance(identifier, str) or not identifier.strip():
            return {'error': 'Invalid identifier provided'}

        if is_valid_hmdb_id(identifier):
            hmdb_id = identifier
            all_names = self.get_all_names(hmdb_id)
            primary_name = self.get_primary_name(hmdb_id)
            confidence_info = {
                'confidence': 1.0,
                'match_type': 'direct_hmdb_id',
                'lookup_method': 'direct_hmdb_id'
            }
        else:
            confidence_info = self.get_hmdb_id_with_confidence(identifier)
            hmdb_id = confidence_info['hmdb_id']

            if not hmdb_id:
                return {'error': f"Could not resolve '{identifier}' to HMDB ID"}

            all_names = confidence_info['all_names']
            primary_name = confidence_info['primary_name']
            confidence_info['lookup_method'] = 'name_to_hmdb_id'

        # Import here to avoid circular imports
        from metabolite_hmdb_lookup import get_diet_advice_by_hmdb_id

        return {
            'hmdb_id': hmdb_id,
            'primary_name': primary_name,
            'all_names': all_names,
            'total_names': len(all_names),
            'confidence_info': confidence_info,
            'has_high_advice': bool(get_diet_advice_by_hmdb_id(hmdb_id, 'high')),
            'has_low_advice': bool(get_diet_advice_by_hmdb_id(hmdb_id, 'low'))
        }
