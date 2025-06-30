#!/usr/bin/env python3
"""
Metabolite Data Enricher

This script focuses solely on enriching metabolite information with synonyms, chemical classes,
and descriptions from HMDB and PubChem. It saves the enriched data to both internal structures
and local JSON files for reuse across the system.

Separated from diet advice generation for better modularity and maintainability.
"""

import argparse
import json
import os
import re
import sys
import time
import copy
import logging
import pickle
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union, Hashable

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from enhanced_hmdb_lookup import EnhancedHMDBLookup
from pubchem_data_retriever import (
    get_compound_description,
    get_compound_classifications,
    get_compound_bioactivity,
    get_compound_literature,
    get_compound_synonyms,
    HEADERS
)

# Constants
ENRICHED_CSV_FILE = 'data/metabolite_enriched_data.csv'

# Configure logging
try:
    os.makedirs('logs', exist_ok=True)
    
    # Configure logging to both console and file
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('logs/metabolite_enricher_debug.log', mode='w')
        ]
    )
except Exception as e:
    print(f"Failed to configure logging: {e}")

# Create logger for this module
logger = logging.getLogger(__name__)

# Load environment variables with override to ensure .env takes precedence
load_dotenv(override=True)
api_key = os.getenv('OPENROUTER_API_KEY')
logger.debug(f"OpenRouter API Key loaded from .env file: {api_key}")
logger.debug(f"Environment variable source confirmation - OPENROUTER_API_KEY is set to: {api_key}")

# Constants
CACHE_FILE = "data/metabolite_enrichment_cache.pkl"
ENRICHED_JSON_FILE = "data/metabolite_enriched_data.json"
ENRICHED_CSV_FILE = "data/enriched_normal_ranges.csv"
RATE_LIMIT_DELAY = 2  # Seconds between API calls

# Perplexity models via OpenRouter for metabolite enrichment
PERPLEXITY_FALLBACK_MODELS = [
    "perplexity/sonar-reasoning",               # ← Now first priority
    "perplexity/sonar-deep-research",
    "perplexity/sonar-reasoning-pro",
    "perplexity/sonar-pro",
    "perplexity/llama-3.1-sonar-large-128k-online"
]

class MetaboliteDataEnricher:
    """Class for enriching metabolite information from multiple data sources."""
    
    def __init__(self, cache_file: str = None, use_perplexity_first: bool = False,
                 refresh_cache: bool = False, force_pubchem: bool = False,
                 include_health_conditions: bool = False, include_food_recommendations: bool = False,
                 save_all_to_json: bool = False, output_dir: str = 'output'):
        """Initialize the MetaboliteDataEnricher.
        
        Args:
            cache_file (str, optional): Path to cache file
            use_perplexity_first (bool): Whether to use Perplexity API first
            refresh_cache (bool): Whether to refresh cache
            force_pubchem (bool): Whether to force PubChem data collection
            include_health_conditions (bool): Whether to include health conditions
            include_food_recommendations (bool): Whether to include food recommendations
            save_all_to_json (bool): Whether to save all data to JSON
            output_dir (str): Directory to save output files
        """
        self.cache_file = cache_file or CACHE_FILE
        self.use_perplexity_first = use_perplexity_first
        self.refresh_cache = refresh_cache
        self.force_pubchem = force_pubchem
        self.cache = {}
        self.hmdb_lookup = EnhancedHMDBLookup()
        self.enriched_data = []
        self.include_health_conditions = include_health_conditions
        self.include_food_recommendations = include_food_recommendations
        self.openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
        self.save_all_to_json = save_all_to_json
        
        # Initialize output directory
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Load cache if it exists
        self._load_cache()

    def _load_cache(self) -> None:
        """Load cache from file."""
        try:
            if Path(self.cache_file).exists():
                with open(self.cache_file, 'rb') as f:
                    self.cache = pickle.load(f)
                logger.info(f"Loaded cache with {len(self.cache)} entries")
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")

    def _save_cache(self) -> None:
        """Save cache to file."""
        try:
            Path(self.cache_file).parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.cache, f)
            logger.info(f"Saved cache with {len(self.cache)} entries")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def save_cache(self):
        """Save cache to file."""
        try:
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.cache, f)
                logger.info(f"Saved cache to {self.cache_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
            return False

    def get_perplexity_metabolite_info(self, hmdb_id: str, metabolite_name: str) -> Dict[str, Any]:
        """
        Get metabolite information using Perplexity LLMs via OpenRouter.

        Args:
            hmdb_id (str): HMDB ID (e.g., 'HMDB0000687')
            metabolite_name (str): Metabolite name

        Returns:
            Dict containing synonyms, classes, and description from Perplexity
        """
        # Start timing
        start_time = time.time()
        
        cache_key = f"perplexity_{hmdb_id}_{metabolite_name}"
        if cache_key in self.cache and not self.refresh_cache:
            logger.debug(f"Using cached Perplexity data for {metabolite_name} (HMDB ID: {hmdb_id})")
            result = self.cache[cache_key]
            # Add timing information for cached results
            if 'timing' not in result:
                result['timing'] = {
                    'source': 'perplexity',
                    'elapsed_seconds': 0.0,
                    'from_cache': True
                }
            return result
        
        if self.refresh_cache:
            logger.debug(f"Bypassing cache for Perplexity data for {metabolite_name} (HMDB ID: {hmdb_id})")

        try:
            # Create comprehensive prompt for metabolite information
            prompt = self._create_perplexity_metabolite_prompt(hmdb_id, metabolite_name)

            logger.info(f"Fetching Perplexity data for {metabolite_name} ({hmdb_id})")

            # Call Perplexity via OpenRouter with fallback
            response = self._call_perplexity_api_with_fallback(prompt)

            if response:
                # Parse the response
                info = self._parse_perplexity_response(response, hmdb_id, metabolite_name)
                
                # Calculate time taken for successful responses
                end_time = time.time()
                elapsed_time = end_time - start_time
                
                # Add timing information
                info['timing'] = {
                    'source': 'perplexity',
                    'elapsed_seconds': round(elapsed_time, 2),
                    'from_cache': False,
                    'success': True
                }
                
                logger.debug(f"Perplexity API fetch took {elapsed_time:.2f} seconds for {metabolite_name} ({hmdb_id})")

                # Cache the result
                self.cache[cache_key] = info

                # Rate limiting
                time.sleep(RATE_LIMIT_DELAY)

                return info
            else:
                logger.warning(f"No response from Perplexity for {metabolite_name}")
                empty_info = self._create_empty_perplexity_info(hmdb_id)
                
                # Calculate time taken even for failures
                end_time = time.time()
                elapsed_time = end_time - start_time
                
                # Add timing information
                empty_info['timing'] = {
                    'source': 'perplexity',
                    'elapsed_seconds': round(elapsed_time, 2),
                    'from_cache': False,
                    'success': False
                }
                
                self.cache[cache_key] = empty_info
                return empty_info

        except Exception as e:
            logger.error(f"Error fetching Perplexity data for {metabolite_name}: {e}")
            empty_info = self._create_empty_perplexity_info(hmdb_id)
            empty_info['error'] = str(e)
            
            # Calculate time taken even for errors
            end_time = time.time()
            elapsed_time = end_time - start_time
            
            # Add timing information
            empty_info['timing'] = {
                'source': 'perplexity',
                'elapsed_seconds': round(elapsed_time, 2),
                'from_cache': False,
                'success': False,
                'error': True
            }
            
            self.cache[cache_key] = empty_info
            return empty_info

    def _create_perplexity_metabolite_prompt(self, hmdb_id: str, metabolite_name: str) -> str:
        """Create a comprehensive prompt for Perplexity to get metabolite information."""
        base_prompt = f"""Please provide comprehensive information about the metabolite "{metabolite_name}" (HMDB ID: {hmdb_id}) in JSON format.

Include the following information:
1. Alternative names and synonyms (common names, chemical names, trade names)
2. Chemical classification and categories (chemical class, super class, sub class)
3. Biological description and function
4. Chemical properties (molecular formula, molecular weight if available)
5. Metabolic pathways or biological roles"""

        # Add health conditions request if flag is enabled
        if self.include_health_conditions:
            base_prompt += """
6. Health conditions associated with high concentrations of this metabolite
7. Health conditions associated with low concentrations of this metabolite"""
            
        # Add food recommendations request if flag is enabled
        if self.include_food_recommendations:
            base_prompt += """
8. Specific food items to avoid when this metabolite is too high
9. Specific food items to consume when this metabolite is too high
10. Specific food items to avoid when this metabolite is too low
11. Specific food items to consume when this metabolite is too low"""

        base_prompt += """

Please format your response as a JSON object with these exact keys:
{
  "synonyms": ["list of alternative names and synonyms"],
  "chemical_classes": ["list of chemical classifications from broad to specific"],
  "description": "comprehensive description of the metabolite's biological function and significance",
  "molecular_formula": "chemical formula if available",
  "molecular_weight": "molecular weight if available",
  "biological_roles": ["list of key biological functions or pathways"],
  "common_name": "most commonly used name",
  "iupac_name": "IUPAC systematic name if available\""""

        # Add health condition fields if requested
        if self.include_health_conditions:
            base_prompt += """,
  "high_conditions": ["list of health conditions, diseases, or disorders associated with elevated levels of this metabolite"],
  "low_conditions": ["list of health conditions, diseases, or disorders associated with deficient levels of this metabolite"]"""
            
        # Add food recommendation fields if requested
        if self.include_food_recommendations:
            base_prompt += """,
  "avoid_high": ["list of specific food items to avoid when this metabolite is too high"],
  "consume_high": ["list of specific food items to consume when this metabolite is too high"],
  "avoid_low": ["list of specific food items to avoid when this metabolite is too low"],
  "consume_low": ["list of specific food items to consume when this metabolite is too low"]"""

        base_prompt += """
}

Focus on providing accurate, scientific information from reliable biochemical and metabolomics databases. If certain information is not available, use empty strings or empty arrays for those fields."""

        if self.include_health_conditions:
            base_prompt += """ For health conditions, include both direct causative relationships and correlative associations found in medical literature."""
            
        if self.include_food_recommendations:
            base_prompt += """ For food recommendations, please ensure you provide specific food items in all four arrays (avoid_high, consume_high, avoid_low, consume_low). Focus on specific food items rather than broad categories, and include foods with scientific evidence supporting their effect on this metabolite's levels. Even if limited research exists, provide at least 3-5 food items in each array based on the best available nutritional science and metabolic pathways."""

        return base_prompt

    def _call_perplexity_api_with_fallback(self, prompt: str, timeout: int = 120) -> Optional[str]:
        """Call Perplexity API via OpenRouter with model fallback."""
        headers = {
            'Authorization': f'Bearer {self.openrouter_api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://metabolite-enricher.local',
            'X-Title': 'Metabolite Data Enricher'
        }
        
        logger.debug(f"OpenRouter API Key being used: {self.openrouter_api_key[:5]}...{self.openrouter_api_key[-5:] if self.openrouter_api_key else 'None'}")

        for model in PERPLEXITY_FALLBACK_MODELS:
            try:
                logger.info(f"Trying Perplexity model: {model}")

                payload = {
                    'model': model,
                    'messages': [
                        {
                            'role': 'user',
                            'content': prompt
                        }
                    ],
                    'max_tokens': 2048
                }

                logger.debug(f"Sending request to OpenRouter API with model {model}")
                response = requests.post(
                    'https://openrouter.ai/api/v1/chat/completions',
                    headers=headers,
                    json=payload,
                    timeout=timeout
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.debug(f"Response data keys: {list(data.keys())}")
                    if 'choices' in data and data['choices']:
                        content = data['choices'][0]['message']['content']
                        logger.info(f"Successfully got response from {model}")
                        logger.debug(f"Response content preview: {content[:100]}...")
                        return content
                    else:
                        logger.warning(f"No choices in response from {model}. Response: {data}")
                        continue
                else:
                    logger.warning(f"HTTP {response.status_code} from {model}: {response.text}")
                    continue

            except Exception as e:
                logger.warning(f"Error with model {model}: {e}")
                continue

        logger.error("All Perplexity models failed")
        return None

    def _parse_perplexity_response(self, response: str, hmdb_id: str, metabolite_name: str) -> Dict[str, Any]:
        """Parse Perplexity response and extract metabolite information."""
        try:
            logger.debug(f"Parsing Perplexity response for {metabolite_name} (HMDB ID: {hmdb_id})")
            logger.debug(f"Response preview: {response[:200]}...")
            
            # Try to extract JSON from the response
            import re

            # Look for JSON block in the response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                logger.debug(f"Found JSON match: {json_str[:100]}...")
                try:
                    parsed_data = json.loads(json_str)
                    logger.debug(f"Successfully parsed JSON with keys: {list(parsed_data.keys())}")
                except json.JSONDecodeError as e:
                    logger.debug(f"Initial JSON parse failed: {e}")
                    # Try to clean up the JSON
                    json_str = json_str.replace('\n', ' ').replace('\r', '')
                    try:
                        parsed_data = json.loads(json_str)
                        logger.debug(f"Successfully parsed JSON after cleanup with keys: {list(parsed_data.keys())}")
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse JSON for {metabolite_name} after cleanup: {e}")
                        logger.debug(f"Problematic JSON string: {json_str}")
                        return self._create_empty_perplexity_info(hmdb_id)
            else:
                logger.warning(f"No JSON found in response for {metabolite_name}")
                return self._create_empty_perplexity_info(hmdb_id)

            # Extract information from parsed data
            info = {
                'hmdb_id': hmdb_id,
                'synonyms': parsed_data.get('synonyms', []),
                'chemical_classes': parsed_data.get('chemical_classes', []),
                'description': parsed_data.get('description', ''),
                'molecular_formula': parsed_data.get('molecular_formula', ''),
                'molecular_weight': parsed_data.get('molecular_weight', ''),
                'biological_roles': parsed_data.get('biological_roles', []),
                'common_name': parsed_data.get('common_name', ''),
                'iupac_name': parsed_data.get('iupac_name', ''),
                'source': 'Perplexity',
                'timestamp': datetime.now().isoformat(),
                'success': True,
                'raw_response': response
            }
            
            # Add health conditions if requested
            if self.include_health_conditions:
                info['high_conditions'] = parsed_data.get('high_conditions', [])
                info['low_conditions'] = parsed_data.get('low_conditions', [])
                
            # Add food recommendations if requested
            if self.include_food_recommendations:
                info['avoid_high'] = parsed_data.get('avoid_high', [])
                info['consume_high'] = parsed_data.get('consume_high', [])
                info['avoid_low'] = parsed_data.get('avoid_low', [])
                info['consume_low'] = parsed_data.get('consume_low', [])

            logger.debug(f"Successfully extracted Perplexity info for {metabolite_name}")
            logger.debug(f"Synonyms: {len(info['synonyms'])}, Classes: {len(info['chemical_classes'])}, Description length: {len(info['description'])}")

            return info

        except Exception as e:
            logger.error(f"Error parsing Perplexity response for {metabolite_name}: {e}")
            logger.debug(f"Raw response: {response}")

            # Fallback: create basic info with raw response
            return {
                'hmdb_id': hmdb_id,
                'synonyms': [],
                'chemical_classes': [],
                'description': '',
                'molecular_formula': '',
                'molecular_weight': '',
                'biological_roles': [],
                'common_name': '',
                'iupac_name': '',
                'source': 'Perplexity',
                'timestamp': datetime.now().isoformat(),
                'success': False,
                'error': str(e),
                'raw_response': response
            }

    def _create_empty_perplexity_info(self, hmdb_id: str) -> Dict[str, Any]:
        """Create empty Perplexity info structure."""
        info = {
            'hmdb_id': hmdb_id,
            'synonyms': [],
            'chemical_classes': [],
            'description': '',
            'molecular_formula': '',
            'molecular_weight': '',
            'biological_roles': [],
            'common_name': '',
            'iupac_name': '',
            'source': 'Perplexity',
            'timestamp': datetime.now().isoformat(),
            'success': False
        }

        # Add health conditions if requested
        if self.include_health_conditions:
            info['high_conditions'] = []
            info['low_conditions'] = []
            
        # Add food recommendations if requested
        if self.include_food_recommendations:
            info['avoid_high'] = []
            info['consume_high'] = []
            info['avoid_low'] = []
            info['consume_low'] = []

        return info

    def get_hmdb_info(self, hmdb_id: str) -> Dict[str, Any]:
        """
        Get HMDB metabolite information using the EnhancedHMDBLookup class.

        Args:
            hmdb_id (str): HMDB ID (e.g., 'HMDB0000687')

        Returns:
            Dict containing synonyms, classes, and description
        """
        logger.info(f"Getting HMDB info for {hmdb_id} using EnhancedHMDBLookup")
        
        # Use the EnhancedHMDBLookup to get HMDB data
        info = self.hmdb_lookup.get_hmdb_info(hmdb_id) if self.hmdb_lookup is not None else {}
        
        # Update our cache with the result from EnhancedHMDBLookup
        if hmdb_id not in self.cache and info.get('success', False):
            self.cache[hmdb_id] = info
            
        return info

    def get_pubchem_info(self, metabolite_name: str, hmdb_id: str = "") -> Dict[str, Any]:
        """Get PubChem information for a compound.
        
        Args:
            metabolite_name (str): Name of the metabolite
            hmdb_id (str, optional): HMDB ID if available
            
        Returns:
            Dict: PubChem data
        """
        result = {}
        
        try:
            # First try to get PubChem CID from HMDB data
            cid = ""
            if hmdb_id:
                hmdb_data = self.hmdb_lookup.get_hmdb_info(hmdb_id)
                if hmdb_data and 'pubchem_cid' in hmdb_data:
                    cid = hmdb_data['pubchem_cid']
            
            # If no CID from HMDB, try to search by name
            if not cid:
                cid = self._search_pubchem_by_name(metabolite_name)
            
            if cid:
                logger.info(f"Fetching PubChem data for CID {cid}")
                pubchem_data = self.get_combined_pubchem_info(cid)
                if pubchem_data:
                    result.update(pubchem_data)
                    result['pubchem_cid'] = cid
        except Exception as e:
            logger.error(f"Error fetching PubChem data for {metabolite_name} (HMDB: {hmdb_id}): {str(e)}")
        
        return result

    def get_combined_pubchem_info(self, cid: str) -> Dict[str, Any]:
        """Get comprehensive PubChem information using helper functions.
        
        Args:
            cid (str): PubChem Compound ID
            
        Returns:
            Dict: Combined PubChem data
        """
        result = {}
        
        try:
            logger.info(f"Fetching comprehensive PubChem data for CID {cid}")
            
            # Get compound description and properties
            description_data = get_compound_description(cid)
            if description_data:
                result['compound_description'] = description_data.get('description', '')
                result['chemical_properties'] = description_data.get('properties', {})
            
            # Get compound classifications and taxonomy
            classifications_data = get_compound_classifications(cid)
            if classifications_data:
                result['classifications'] = classifications_data.get('classifications', {})
                result['taxonomy'] = classifications_data.get('taxonomy', {})
            
            # Get compound bioactivity data
            bioactivity_data = get_compound_bioactivity(cid)
            if bioactivity_data:
                result['bioactivity'] = bioactivity_data.get('bioactivity', [])
            
            # Get compound literature data
            literature_data = get_compound_literature(cid)
            if literature_data:
                result['literature'] = literature_data.get('literature', [])
            
            # Get compound synonyms
            synonyms_data = get_compound_synonyms(cid)
            if synonyms_data:
                result['synonyms'] = synonyms_data.get('synonyms', [])
        except Exception as e:
            logger.error(f"Error fetching comprehensive PubChem data for CID {cid}: {str(e)}")
        
        return result

    def process_metabolites_from_csv(self, csv_file: str, sample_size: int = None) -> bool:
        """Process metabolites from a CSV file.
        
        Args:
            csv_file (str): Path to CSV file
            sample_size (int, optional): Number of metabolites to process
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            df = pd.read_csv(csv_file)
            logger.info(f"Found {len(df)} metabolites in CSV file")
            
            if sample_size:
                df = df.head(sample_size)
            
            for index, row in df.iterrows():
                logger.info(f"Processing metabolite {index + 1} of {len(df)}")
                try:
                    metabolite_name = row['Metabolite']
                    hmdb_id = row['HMDB_ID']
                    
                    if pd.isna(metabolite_name) or pd.isna(hmdb_id):
                        logger.warning(f"Skipping row {index}: missing data")
                        continue
                    
                    # Process the metabolite
                    enriched_data = self.enrich_metabolite(metabolite_name, hmdb_id)
                    if enriched_data:
                        # Save individual JSON file
                        sanitized_name = metabolite_name.lower().replace(' ', '_')
                        output_file = os.path.join(self.output_dir, f"{sanitized_name}.json")
                        self.save_enriched_data_to_json(output_file, enriched_data)
                        
                        # Add to enriched data list
                        self.enriched_data.append(enriched_data)
                except Exception as e:
                    logger.error(f"Error processing metabolite {metabolite_name}: {e}")
                    continue
            
            # Save cache after processing
            self.save_cache()
            return True
            
        except Exception as e:
            logger.error(f"Error processing CSV file: {e}")
            return False

    def enrich_metabolite(self, metabolite_name: str, hmdb_id: str = "") -> Dict[str, Any]:
        """Enrich a single metabolite with information from all sources.
        
        Args:
            metabolite_name (str): Name of the metabolite
            hmdb_id (str, optional): HMDB ID if available
            
        Returns:
            dict: Enriched metabolite data
        """
        # Start timing the entire enrichment process
        enrich_start_time = time.time()
        logger.info(f"Enriching {metabolite_name} ({hmdb_id})")

        # Initialize info containers
        perplexity_info: Dict[str, Any] = {}
        hmdb_info: Dict[str, Any] = {}
        pubchem_info: Dict[str, Any] = {}

        # Always get HMDB information first
        hmdb_info = self.get_hmdb_info(hmdb_id)
        hmdb_success = bool(hmdb_info)
        
        # If HMDB lookup failed, try Perplexity first for better context
        if not hmdb_success and self.use_perplexity_first:
            perplexity_info = self.get_perplexity_metabolite_info(hmdb_id, metabolite_name)

        # Get PubChem information using the metabolite name
        pubchem_info = self.get_pubchem_info(metabolite_name, hmdb_id)
        pubchem_success = bool(pubchem_info)

        # If we haven't tried Perplexity yet and other sources failed, try it now
        if not hmdb_success and not pubchem_success and not self.use_perplexity_first:
            perplexity_info = self.get_perplexity_metabolite_info(hmdb_id, metabolite_name)

        perplexity_success = bool(perplexity_info)

        # Construct enriched metabolite data
        enriched_metabolite = {
            'name': metabolite_name,
            'hmdb_id': hmdb_id,
            'data_sources': {
                'hmdb_success': hmdb_success,
                'pubchem_success': pubchem_success,
                'perplexity_success': perplexity_success,
                'has_contextual_info': perplexity_success,
                'primary_source': 'perplexity' if perplexity_success else 'hmdb'
            },
            'hmdb_data': hmdb_info if hmdb_info else {},
            'pubchem_data': pubchem_info if pubchem_info else {},
            'perplexity_data': perplexity_info if perplexity_info else {}
        }

        # Calculate total enrichment time
        enrich_end_time = time.time()
        total_enrichment_time = enrich_end_time - enrich_start_time
        
        # Add timing information
        enriched_metabolite['timing_summary'] = {
            'total_enrichment_seconds': round(total_enrichment_time, 2),
        }
        
        logger.debug(f"Total enrichment took {total_enrichment_time:.2f} seconds for {metabolite_name} ({hmdb_id})")
        
        # Return the enriched data
        return enriched_metabolite

    def _search_pubchem_by_name(self, metabolite_name: str) -> Optional[str]:
        """Search PubChem for a compound by name and return the CID."""
        try:
            search_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{metabolite_name}/cids/JSON"
            response = requests.get(search_url, headers=HEADERS, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if 'IdentifierList' in data and 'CID' in data['IdentifierList']:
                    cid = str(data['IdentifierList']['CID'][0])
                    logger.info(f"Found PubChem CID {cid} for {metabolite_name} by name search.")
                    return cid
            logger.warning(f"Could not find PubChem CID for {metabolite_name} by name search.")
            return None
        except Exception as e:
            logger.error(f"Error searching PubChem for {metabolite_name}: {e}")
            return None

    def process_single_metabolite(self, metabolite_name: str) -> bool:
        """
        Process a single metabolite by name and save its enriched data.

        Args:
            metabolite_name (str): Name of the metabolite to process

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get HMDB ID for metabolite name
            hmdb_id = self.hmdb_lookup.get_hmdb_id(metabolite_name)
            if not hmdb_id:
                logger.error(f"Could not find HMDB ID for metabolite: {metabolite_name}")
                return False

            # Get enriched data
            enriched_data = self.enrich_metabolite(metabolite_name, hmdb_id)
            if not enriched_data:
                logger.error(f"Failed to enrich data for metabolite: {metabolite_name}")
                return False

            # Add to enriched data list
            self.enriched_data.append(enriched_data)

            # Save individual JSON file
            output_file = os.path.join(self.output_dir, f"{metabolite_name.lower().replace(' ', '_')}.json")
            self.save_enriched_data_to_json(output_file, enriched_data)

            logger.info(f"Successfully processed metabolite: {metabolite_name}")
            return True

        except Exception as e:
            logger.error(f"Error processing metabolite {metabolite_name}: {e}")
            return False

    def save_enriched_data_to_json(self, output_file: str, data: Dict[str, Any] = None) -> bool:
        """
        Save enriched data to a JSON file.

        Args:
            output_file (str): Path to save the JSON file
            data (Dict, optional): Data to save, if None, use self.enriched_data

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create output directory if it doesn't exist
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            # Use provided data or self.enriched_data
            data_to_save = data if data is not None else self.enriched_data
            
            # Save to JSON
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2)
            logger.info(f"Saved enriched data to {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving enriched data to JSON: {e}")
            return False

    def save_enriched_data_by_name_to_json(self) -> bool:
        """
        Save all enriched data to a JSON file organized by metabolite name.
        The file will be saved to data/metabolite_enriched_data_by_name.json.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create data directory if it doesn't exist
            os.makedirs('data', exist_ok=True)
            output_file = 'data/metabolite_enriched_data_by_name.json'

            # Convert list to dictionary with metabolite names as keys
            data_by_name = {}
            for item in self.enriched_data:
                if isinstance(item, dict) and 'name' in item:
                    data_by_name[item['name']] = item

            # Save enriched data to JSON
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data_by_name, f, indent=2)

            logger.info(f"Saved enriched data by name to {output_file}")
            return True

        except Exception as e:
            logger.error(f"Error saving enriched data by name to JSON: {e}")
            return False

    def save_enriched_data_to_csv(self, output_file: str = ENRICHED_CSV_FILE) -> bool:
        """
        Save enriched data to a CSV file.

        Args:
            output_file (str): Path to save the CSV file

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Convert enriched data to DataFrame
            df = pd.DataFrame(self.enriched_data)
            
            # Create output directory if it doesn't exist
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            # Save to CSV
            df.to_csv(output_file, index=False)
            logger.info(f"Saved enriched data to {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving enriched data to CSV: {e}")
            return False
