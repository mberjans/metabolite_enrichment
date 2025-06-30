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
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
import logging
from datetime import datetime
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import pickle

# Configure logging
# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Configure logging to both console and file
logging.basicConfig(
    level=logging.DEBUG,  # Temporarily set to DEBUG for investigation
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/metabolite_enricher_debug.log', mode='w')
    ]
)
logger = logging.getLogger('metabolite_data_enricher')

# Load environment variables with override to ensure .env takes precedence
load_dotenv(override=True)
logger.debug(f"OpenRouter API Key loaded from .env file: {os.getenv('OPENROUTER_API_KEY')}")
logger.debug(f"Environment variable source confirmation - OPENROUTER_API_KEY is set to: {os.getenv('OPENROUTER_API_KEY')}")

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

    def __init__(self, cache_file: str = CACHE_FILE, use_perplexity_first: bool = False, refresh_cache: bool = False, force_pubchem: bool = False, include_health_conditions: bool = False, include_food_recommendations: bool = False):
        self.cache_file = cache_file
        self.cache = self.load_cache()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Metabolite Research Tool) AppleWebKit/537.36'
        })
        self.enriched_data = {}
        self.enriched_data_by_name = {}
        self.use_perplexity_first = use_perplexity_first
        self.refresh_cache = refresh_cache
        self.force_pubchem = force_pubchem
        self.include_health_conditions = include_health_conditions
        self.include_food_recommendations = include_food_recommendations
        self.openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
        
        if self.refresh_cache:
            logger.info("Cache refresh mode enabled - will bypass cache for Perplexity API calls")

        if self.use_perplexity_first and not self.openrouter_api_key:
            logger.warning("OPENROUTER_API_KEY not found. Falling back to HMDB scraping only.")
            self.use_perplexity_first = False

    def load_cache(self) -> Dict:
        """Load cached metabolite data to avoid repeated API calls."""
        if Path(self.cache_file).exists():
            try:
                with open(self.cache_file, 'rb') as f:
                    cache = pickle.load(f)
                logger.info(f"Loaded cache with {len(cache)} entries")
                return cache
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
        return {}

    def save_cache(self):
        """Save cache to disk."""
        try:
            Path(self.cache_file).parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.cache, f)
            logger.info(f"Saved cache with {len(self.cache)} entries")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

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
                response = self.session.post(
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
        Scrape HMDB metabolite page for detailed information.

        Args:
            hmdb_id (str): HMDB ID (e.g., 'HMDB0000687')

        Returns:
            Dict containing synonyms, classes, and description
        """
        # Start timing
        start_time = time.time()
        
        if hmdb_id in self.cache:
            result = self.cache[hmdb_id]
            # Add timing information for cached results
            if 'timing' not in result:
                result['timing'] = {
                    'source': 'hmdb',
                    'elapsed_seconds': 0.0,
                    'from_cache': True
                }
            return result

        # Skip NOID metabolites for HMDB lookup
        if 'NOID' in hmdb_id:
            return self._create_empty_hmdb_info(hmdb_id)

        try:
            url = f"https://hmdb.ca/metabolites/{hmdb_id}"
            logger.info(f"Fetching HMDB data for {hmdb_id}")

            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract information
            info = {
                'hmdb_id': hmdb_id,
                'synonyms': self._extract_synonyms(soup),
                'chemical_classes': self._extract_chemical_classes(soup),
                'description': self._extract_description(soup),
                'iupac_name': self._extract_iupac_name(soup),
                'common_name': self._extract_common_name(soup),
                'kingdom': self._extract_taxonomy_field(soup, 'Kingdom'),
                'super_class': self._extract_taxonomy_field(soup, 'Super Class'),
                'class': self._extract_taxonomy_field(soup, 'Class'),
                'sub_class': self._extract_taxonomy_field(soup, 'Sub Class'),
                'direct_parent': self._extract_taxonomy_field(soup, 'Direct Parent'),
                'source': 'HMDB',
                'timestamp': datetime.now().isoformat(),
                'success': True
            }

            # Calculate time taken
            end_time = time.time()
            elapsed_time = end_time - start_time
            
            # Add timing information
            info['timing'] = {
                'source': 'hmdb',
                'elapsed_seconds': round(elapsed_time, 2),
                'from_cache': False
            }
            
            logger.debug(f"HMDB fetch took {elapsed_time:.2f} seconds for {hmdb_id}")
            
            # Cache the result
            self.cache[hmdb_id] = info

            # Rate limiting
            time.sleep(RATE_LIMIT_DELAY)

            return info

        except Exception as e:
            logger.error(f"Error fetching HMDB data for {hmdb_id}: {e}")
            empty_info = self._create_empty_hmdb_info(hmdb_id)
            empty_info['error'] = str(e)
            
            # Calculate time taken even for errors
            end_time = time.time()
            elapsed_time = end_time - start_time
            
            # Add timing information
            empty_info['timing'] = {
                'source': 'hmdb',
                'elapsed_seconds': round(elapsed_time, 2),
                'from_cache': False,
                'success': False,
                'error': True
            }
            
            self.cache[hmdb_id] = empty_info
            return empty_info

    def get_pubchem_info(self, metabolite_name: str, hmdb_id: str = "") -> Dict[str, Any]:
        """
        Get additional information from PubChem API.

        Args:
            metabolite_name (str): Name of the metabolite
            hmdb_id (str): HMDB ID for cache key

        Returns:
            Dict containing additional chemical information
        """
        # Start timing
        start_time = time.time()
        
        cache_key = f"pubchem_{hmdb_id}_{metabolite_name}"
        if cache_key in self.cache and not self.refresh_cache:
            logger.debug(f"Using cached PubChem data for {metabolite_name} (HMDB ID: {hmdb_id})")
            result = self.cache[cache_key]
            # Add timing information for cached results
            if 'timing' not in result:
                result['timing'] = {
                    'source': 'pubchem',
                    'elapsed_seconds': 0.0,
                    'from_cache': True
                }
            return result
        
        if self.refresh_cache:
            logger.debug(f"Bypassing cache for PubChem data for {metabolite_name} (HMDB ID: {hmdb_id})")

        try:
            data = None
            
            # First try searching by HMDB ID if available
            if hmdb_id and hmdb_id != 'NOID00000':
                try:
                    # Try direct lookup by HMDB ID using xref endpoint (most reliable method)
                    search_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/xref/RegistryID/{hmdb_id}/JSON"
                    logger.info(f"Searching PubChem by HMDB ID: {hmdb_id} for {metabolite_name}")
                    response = self.session.get(search_url, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    logger.debug(f"PubChem HMDB ID search response for {hmdb_id}: {response.text[:200]}...")
                except Exception as hmdb_search_error:
                    logger.warning(f"Failed to find {metabolite_name} (HMDB ID: {hmdb_id}) in PubChem by HMDB ID, falling back to name search: {hmdb_search_error}")
            
            # If HMDB ID search failed or wasn't available, try by name
            if data is None:
                try:
                    from urllib.parse import quote
                    search_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{quote(metabolite_name)}/JSON"
                    logger.info(f"Searching PubChem by name: {metabolite_name}")
                    response = self.session.get(search_url, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    logger.debug(f"PubChem name search response for {metabolite_name}: {response.text[:200]}...")
                except Exception as name_search_error:
                    logger.error(f"Error fetching PubChem data for {metabolite_name}: {name_search_error}")
                    # Return empty result with error info
                    result = {
                        'pubchem_cid': '',
                        'molecular_formula': '',
                        'molecular_weight': '',
                        'success': False,
                        'source': 'PubChem',
                        'error': str(name_search_error)
                    }
                    self.cache[cache_key] = result
                    return result

            info = {
                'pubchem_cid': '',
                'molecular_formula': '',
                'molecular_weight': '',
                'canonical_smiles': '',
                'inchi': '',
                'pubchem_synonyms': [],
                'compound_description': '',
                'biological_summary': '',
                'pharmacology': '',
                'literature_abstracts': [],
                'source': 'PubChem',
                'timestamp': datetime.now().isoformat(),
                'success': True
            }

            if 'PC_Compounds' in data and data['PC_Compounds']:
                compound = data['PC_Compounds'][0]

                # Extract CID
                cid = ''
                if 'id' in compound and 'id' in compound['id'] and 'cid' in compound['id']['id']:
                    cid = str(compound['id']['id']['cid'])
                    info['pubchem_cid'] = cid
                    
                    # Fetch and store PubChem synonyms
                    try:
                        pubchem_synonyms = self._extract_pubchem_synonyms(cid)
                        if pubchem_synonyms:
                            info['pubchem_synonyms'] = pubchem_synonyms
                            # Also add to all_synonyms
                            if 'all_synonyms' not in info:
                                info['all_synonyms'] = []
                            for synonym in pubchem_synonyms:
                                if synonym not in info['all_synonyms']:
                                    info['all_synonyms'].append(synonym)
                    except Exception as e:
                        logger.error(f"Error extracting PubChem synonyms for CID {cid}: {e}")
                    
                    # Fetch additional PubChem data (descriptions, summaries, etc.)
                    try:
                        self._fetch_pubchem_additional_data(cid, info)
                    except Exception as e:
                        logger.error(f"Error fetching additional PubChem data for CID {cid}: {e}")

                # Extract molecular formula
                if 'props' in compound:
                    for prop in compound['props']:
                        if 'urn' in prop and 'label' in prop['urn'] and prop['urn']['label'] == 'Molecular Formula':
                            if 'value' in prop and 'sval' in prop['value']:
                                info['molecular_formula'] = prop['value']['sval']
                        
                        elif 'urn' in prop and 'label' in prop['urn'] and prop['urn']['label'] == 'Molecular Weight':
                            if 'value' in prop and 'fval' in prop['value']:
                                info['molecular_weight'] = str(prop['value']['fval'])
                        
                        elif 'urn' in prop and 'label' in prop['urn'] and prop['urn']['label'] == 'SMILES' and 'name' in prop['urn'] and prop['urn']['name'] == 'Canonical':
                            if 'value' in prop and 'sval' in prop['value']:
                                info['canonical_smiles'] = prop['value']['sval']
                        
                        elif 'urn' in prop and 'label' in prop['urn'] and prop['urn']['label'] == 'InChI':
                            if 'value' in prop and 'sval' in prop['value']:
                                info['inchi'] = prop['value']['sval']

            # Add timing information
            elapsed_time = time.time() - start_time
            info['timing'] = {
                'source': 'pubchem',
                'elapsed_seconds': elapsed_time,
                'from_cache': False
            }
            
            # Cache the result
            self.cache[cache_key] = info
            return info
            
        except Exception as e:
            logger.error(f"Error in get_pubchem_info for {metabolite_name}: {e}")
            # Return empty result with error info
            result = {
                'pubchem_cid': '',
                'molecular_formula': '',
                'molecular_weight': '',
                'success': False,
                'source': 'PubChem',
                'error': str(e)
            }
            self.cache[cache_key] = result
            return result

    def _extract_pubchem_synonyms(self, cid: str) -> list:
        """
        Extract synonyms for a compound from PubChem using the PUG View API.
        
        Args:
            cid: PubChem Compound ID
            
        Returns:
            List of synonyms
        """
        if not cid:
            return []
        
        try:
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON?heading=Synonyms"
            response = self.session.get(url, timeout=30)
            
            if response.status_code != 200:
                logger.warning(f"Failed to get PubChem synonyms for CID {cid}: {response.status_code}")
                return []
            
            data = response.json()
            synonyms = []
            
            if "Record" in data and "Section" in data["Record"]:
                for section in data["Record"]["Section"]:
                    if section.get("TOCHeading") == "Names and Identifiers":
                        for subsection in section.get("Section", []):
                            if subsection.get("TOCHeading") == "Synonyms":
                                for info in subsection.get("Information", []):
                                    if "Value" in info and "StringWithMarkup" in info["Value"]:
                                        for markup in info["Value"]["StringWithMarkup"]:
                                            if "String" in markup:
                                                synonyms.append(markup["String"])
                                    elif "Value" in info and "String" in info["Value"]:
                                        synonyms.append(info["Value"]["String"])
            
            # Clean up synonyms and remove duplicates
            cleaned_synonyms = []
            seen = set()
            for syn in synonyms:
                cleaned = syn.strip()
                if cleaned and cleaned.lower() not in seen and len(cleaned) < 100:
                    cleaned_synonyms.append(cleaned)
                    seen.add(cleaned.lower())
            
            logger.info(f"Extracted {len(cleaned_synonyms)} unique synonyms from PubChem for CID {cid}")
            return cleaned_synonyms[:20]  # Limit to top 20 synonyms
        
        except Exception as e:
            logger.error(f"Error extracting PubChem synonyms for CID {cid}: {e}")
            return []

    def _fetch_pubchem_additional_data(self, cid: str, info: Dict[str, Any]) -> None:
        """
        Fetch additional data from PubChem PUG-View API.
        
        Args:
            cid (str): PubChem Compound ID
            info (Dict): Dictionary to update with additional information
        """
        try:
            # Use PUG-View to get additional information
            pugview_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"
            logger.info(f"Fetching additional PubChem data for CID {cid}")
            
            response = self.session.get(pugview_url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            logger.debug(f"PubChem PUG-View response for CID {cid}: {str(data)[:200]}...")
            
            # Extract sections from the PUG-View data
            if 'Record' in data and 'Section' in data['Record']:
                sections = data['Record']['Section']
                
                # Debug: Log all available sections
                logger.debug(f"Available PubChem sections for CID {cid}:")
                for i, section in enumerate(sections):
                    section_name = section.get('TOCHeading', 'Unknown')
                    logger.debug(f"  Section {i}: {section_name}")
                    if 'Section' in section:
                        for j, subsection in enumerate(section['Section']):
                            subsection_name = subsection.get('TOCHeading', 'Unknown')
                            logger.debug(f"    Subsection {j}: {subsection_name}")
                
                # Process each section to extract relevant information
                for section in sections:
                    section_name = section.get('TOCHeading', '')
                    
                    # Extract compound description from Names and Identifiers or Record Description
                    if section_name == 'Names and Identifiers':
                        description = self._extract_pubchem_section_text(section, 'Description')
                        if not description:
                            # Try to get any text content from this section
                            description = self._extract_any_text_from_section(section)
                        if description:
                            info['compound_description'] = description
                    
                    # Extract biological summary from various biological sections
                    elif section_name in ['Biological Test Results', 'Drug and Medication Information']:
                        biological_text = self._extract_any_text_from_section(section)
                        if biological_text and not info.get('biological_summary'):
                            info['biological_summary'] = biological_text
                    
                    # Extract pharmacology information from Pharmacology and Biochemistry
                    elif section_name == 'Pharmacology and Biochemistry':
                        pharmacology_text = self._extract_any_text_from_section(section)
                        if pharmacology_text:
                            info['pharmacology'] = pharmacology_text
                    
                    # Extract literature information from Literature section
                    elif section_name == 'Literature':
                        abstracts = self._extract_pubchem_literature_enhanced(section)
                        if abstracts:
                            info['literature_abstracts'] = abstracts[:5]  # Limit to 5 abstracts
                    
                    # Also try Associated Disorders and Diseases for biological context
                    elif section_name == 'Associated Disorders and Diseases':
                        disease_text = self._extract_any_text_from_section(section)
                        if disease_text and not info.get('biological_summary'):
                            info['biological_summary'] = disease_text
            
            logger.info(f"Successfully fetched additional PubChem data for CID {cid}")
            
        except Exception as e:
            logger.error(f"Error fetching additional PubChem data for CID {cid}: {e}")

    def _extract_pubchem_section_text(self, section: Dict, target_heading: str) -> str:
        """
        Extract text content from a specific section in PubChem PUG-View data.
        
        Args:
            section (Dict): Section data from PUG-View
            target_heading (str): Heading to look for
            
        Returns:
            str: Extracted text content
        """
        result = ""
        
        # Check if this section matches the target heading
        if section.get('TOCHeading', '') == target_heading and 'Information' in section:
            for info in section['Information']:
                if 'Value' in info and 'StringWithMarkup' in info['Value']:
                    for markup in info['Value']['StringWithMarkup']:
                        if 'String' in markup:
                            result += markup['String'] + " "
        
        # Check subsections recursively
        if 'Section' in section:
            for subsection in section['Section']:
                subsection_text = self._extract_pubchem_section_text(subsection, target_heading)
                if subsection_text:
                    result = subsection_text
                    break
        
        return result.strip()

    def _extract_pubchem_literature(self, section: Dict) -> List[Dict[str, str]]:
        """
        Extract literature abstracts from PubChem PUG-View data.
        
        Args:
            section (Dict): Literature section data from PUG-View
            
        Returns:
            List[Dict[str, str]]: List of abstracts with title, authors, journal, and text
        """
        abstracts = []
        
        # Process literature section
        if 'Section' in section:
            for subsection in section['Section']:
                if subsection.get('TOCHeading', '') == 'Citations' and 'Information' in subsection:
                    for info in subsection['Information']:
                        if 'Reference' in info:
                            reference = info['Reference']
                            abstract = {
                                'title': reference.get('Title', ''),
                                'authors': ', '.join(reference.get('Author', [])),
                                'journal': reference.get('Journal', ''),
                                'year': reference.get('Year', ''),
                                'abstract': ''
                            }
                            
                            # Try to get the abstract text if available
                            if 'Value' in info and 'StringWithMarkup' in info['Value']:
                                for markup in info['Value']['StringWithMarkup']:
                                    if 'String' in markup:
                                        abstract['abstract'] += markup['String'] + " "
                            
                            abstracts.append(abstract)
        
        return abstracts

    def _extract_pubchem_literature_enhanced(self, section: Dict) -> List[Dict[str, str]]:
        """
        Extract literature abstracts from PubChem PUG-View data (enhanced).
        
        Args:
            section (Dict): Literature section data from PUG-View
            
        Returns:
            List[Dict[str, str]]: List of abstracts with title, authors, journal, and text
        """
        abstracts = []
        
        # Process literature section - target actual subsections found in PubChem
        if 'Section' in section:
            for subsection in section['Section']:
                subsection_name = subsection.get('TOCHeading', '')
                
                # Target the actual literature subsections found in PubChem
                if subsection_name in ['Consolidated References', 'NLM Curated PubMed Citations', 
                                     'Springer Nature References', 'Thieme References', 'Wiley References']:
                    
                    if 'Information' in subsection:
                        for info in subsection['Information']:
                            abstract = {}
                            
                            # Extract reference information if available
                            if 'Reference' in info:
                                reference = info['Reference']
                                abstract.update({
                                    'title': reference.get('Title', ''),
                                    'authors': ', '.join(reference.get('Author', [])),
                                    'journal': reference.get('Journal', ''),
                                    'year': str(reference.get('Year', '')),
                                    'doi': reference.get('DOI', ''),
                                    'pubmed_id': reference.get('PMID', ''),
                                    'abstract': ''
                                })
                            
                            # Extract text content from Value field
                            if 'Value' in info:
                                if 'StringWithMarkup' in info['Value']:
                                    for markup in info['Value']['StringWithMarkup']:
                                        if 'String' in markup:
                                            if not abstract.get('abstract'):
                                                abstract['abstract'] = markup['String']
                                            else:
                                                abstract['abstract'] += " " + markup['String']
                                
                                # Also check for direct string values
                                elif 'String' in info['Value']:
                                    if not abstract.get('abstract'):
                                        abstract['abstract'] = info['Value']['String']
                            
                            # Extract title and other metadata from Name field if Reference not available
                            if 'Name' in info and not abstract.get('title'):
                                abstract['title'] = info['Name']
                            
                            # Only add if we have some meaningful content
                            if abstract.get('title') or abstract.get('abstract') or abstract.get('pubmed_id'):
                                abstracts.append(abstract)
                                
                            # Limit to prevent excessive data
                            if len(abstracts) >= 10:
                                break
                
                # Break if we've collected enough abstracts
                if len(abstracts) >= 10:
                    break
        
        return abstracts

    def _extract_any_text_from_section(self, section: Dict) -> str:
        """
        Extract any text content from a PubChem PUG-View section.
        
        Args:
            section (Dict): Section data from PUG-View
            
        Returns:
            str: Extracted text content
        """
        result = ""
        
        # Check if this section has text content
        if 'Information' in section:
            for info in section['Information']:
                if 'Value' in info and 'StringWithMarkup' in info['Value']:
                    for markup in info['Value']['StringWithMarkup']:
                        if 'String' in markup:
                            result += markup['String'] + " "
        
        # Check subsections recursively
        if 'Section' in section:
            for subsection in section['Section']:
                subsection_text = self._extract_any_text_from_section(subsection)
                if subsection_text:
                    result += subsection_text
        
        return result.strip()

    def enrich_metabolite(self, hmdb_id: str, metabolite_name: str) -> Dict[str, Any]:
        """
        Enrich a single metabolite with information from all sources.

        Args:
            hmdb_id (str): HMDB ID
            metabolite_name (str): Metabolite name

        Returns:
            Dict: Complete enriched metabolite information
        """
        # Start timing the entire enrichment process
        enrich_start_time = time.time()
        logger.info(f"Enriching {metabolite_name} ({hmdb_id})")

        # Initialize info containers
        perplexity_info = {}
        hmdb_info = {}
        pubchem_info = {}

        # Always get HMDB information first
        hmdb_info = self.get_hmdb_info(hmdb_id)
        hmdb_success = hmdb_info.get('success', False)
        
        # Always get PubChem information second
        pubchem_info = self.get_pubchem_info(metabolite_name, hmdb_id)
        pubchem_success = pubchem_info.get('success', False)
        
        # Use Perplexity only if both HMDB and PubChem fail (or if explicitly configured to use first)
        if self.use_perplexity_first:
            # Use Perplexity regardless of other sources (if explicitly configured)
            logger.info(f"Using Perplexity for {metabolite_name} (configured to use first)")
            perplexity_info = self.get_perplexity_metabolite_info(hmdb_id, metabolite_name)
        elif not (hmdb_success or pubchem_success):
            # Use Perplexity only as fallback when both HMDB and PubChem failed
            logger.info(f"Using Perplexity as fallback for {metabolite_name} after HMDB and PubChem failed")
            perplexity_info = self.get_perplexity_metabolite_info(hmdb_id, metabolite_name)
        else:
            # Skip Perplexity since at least one of HMDB or PubChem succeeded
            logger.info(f"Skipping Perplexity for {metabolite_name} - using HMDB/PubChem data")
            perplexity_info = self._create_empty_perplexity_info(hmdb_id)

        # Create contextual information for NOID metabolites
        contextual_info = self._create_contextual_info(metabolite_name, hmdb_id)

        # Combine all information
        enriched_metabolite = {
            'hmdb_id': hmdb_id,
            'original_name': metabolite_name,
            'enhanced_name': self._create_enhanced_name(metabolite_name, hmdb_info, contextual_info, perplexity_info),
            'all_synonyms': self._combine_synonyms(hmdb_info, pubchem_info, contextual_info, perplexity_info),
            'chemical_classes': self._get_best_chemical_classes(hmdb_info, perplexity_info),
            'taxonomy': {
                'kingdom': hmdb_info.get('kingdom', ''),
                'super_class': hmdb_info.get('super_class', ''),
                'class': hmdb_info.get('class', ''),
                'sub_class': hmdb_info.get('sub_class', ''),
                'direct_parent': hmdb_info.get('direct_parent', '')
            },
            'chemical_properties': {
                'iupac_name': self._get_best_value([perplexity_info.get('iupac_name', ''), hmdb_info.get('iupac_name', '')]),
                'common_name': self._get_best_value([perplexity_info.get('common_name', ''), hmdb_info.get('common_name', '')]),
                'molecular_formula': self._get_best_value([perplexity_info.get('molecular_formula', ''), pubchem_info.get('molecular_formula', '')]),
                'molecular_weight': self._get_best_value([perplexity_info.get('molecular_weight', ''), pubchem_info.get('molecular_weight', '')]),
                'canonical_smiles': pubchem_info.get('canonical_smiles', ''),
                'inchi': pubchem_info.get('inchi', ''),
                'pubchem_cid': pubchem_info.get('pubchem_cid', ''),
                'compound_description': pubchem_info.get('compound_description', ''),
                'biological_summary': pubchem_info.get('biological_summary', ''),
                'pharmacology': pubchem_info.get('pharmacology', ''),
                'literature_abstracts': pubchem_info.get('literature_abstracts', []),
            },
            'descriptions': {
                'perplexity_description': perplexity_info.get('description', ''),
                'hmdb_description': hmdb_info.get('description', ''),
                'contextual_description': contextual_info.get('description', ''),
                'llm_description': self._create_llm_description(metabolite_name, hmdb_info, contextual_info, perplexity_info)
            },
            'biological_roles': perplexity_info.get('biological_roles', []),
            'database_ids': {
                'hmdb_id': hmdb_id,
                'pubchem_cid': pubchem_info.get('pubchem_cid', '')
            },
            'data_sources': {
                'perplexity_success': perplexity_info.get('success', False),
                'hmdb_success': hmdb_info.get('success', False),
                'pubchem_success': pubchem_info.get('success', False),
                'has_contextual_info': bool(contextual_info.get('enhanced', False)),
                'primary_source': self._determine_primary_source(hmdb_info, pubchem_info, perplexity_info)
            },
            'enrichment_metadata': {
                'enriched_timestamp': datetime.now().isoformat(),
                'enricher_version': '1.0.0'
            }
        }

        # Add health conditions if requested
        if self.include_health_conditions:
            enriched_metabolite['health_conditions'] = {
                'high_conditions': perplexity_info.get('high_conditions', []),
                'low_conditions': perplexity_info.get('low_conditions', [])
            }
            
        # Add food recommendations if requested
        if self.include_food_recommendations:
            enriched_metabolite['food_recommendations'] = {
                'avoid_high': perplexity_info.get('avoid_high', []),
                'consume_high': perplexity_info.get('consume_high', []),
                'avoid_low': perplexity_info.get('avoid_low', []),
                'consume_low': perplexity_info.get('consume_low', [])
            }

        # Calculate total enrichment time
        enrich_end_time = time.time()
        total_enrichment_time = enrich_end_time - enrich_start_time
        
        # Add timing summary to enriched data
        enriched_metabolite['timing_summary'] = {
            'total_enrichment_seconds': round(total_enrichment_time, 2),
            'sources': []
        }
        
        # Collect timing information from all sources
        source_variables = {
            'perplexity': perplexity_info,
            'hmdb': hmdb_info,
            'pubchem': pubchem_info
        }
        
        for source_name, source_data in source_variables.items():
            if source_data and 'timing' in source_data:
                enriched_metabolite['timing_summary']['sources'].append(source_data['timing'])
        
        logger.debug(f"Total enrichment took {total_enrichment_time:.2f} seconds for {metabolite_name} ({hmdb_id})")
        
        # Add source-specific timing data to the enriched_data structure directly
        for source_name, source_data in source_variables.items():
            if source_data and 'timing' in source_data:
                source_key = f"{source_name}_timing"
                enriched_metabolite[source_key] = source_data['timing']
        
        # Return the enriched data
        return enriched_metabolite

    def _extract_synonyms(self, soup: BeautifulSoup) -> List[str]:
        """Extract synonyms from HMDB page."""
        synonyms = []

        # Look for synonyms in specific table row
        synonym_row = soup.find('td', string=re.compile(r'Synonyms', re.I))
        if synonym_row:
            value_cell = synonym_row.find_next_sibling('td')
            if value_cell:
                # Extract all text from the cell, splitting by common delimiters
                text = value_cell.get_text(separator=';')
                if text:
                    parts = re.split(r'[;,\n]', text)
                    for part in parts:
                        clean_part = part.strip()
                        if clean_part and len(clean_part) > 1 and len(clean_part) < 100:
                            synonyms.append(clean_part)

        # Alternative approach: look for a specific section
        if not synonyms:
            synonym_sections = soup.find_all(['td', 'div'], string=re.compile(r'synonym', re.I))
            for section in synonym_sections:
                next_element = section.find_next_sibling()
                if next_element:
                    text = next_element.get_text(strip=True)
                    if text:
                        parts = re.split(r'[;,\n]', text)
                        for part in parts:
                            clean_part = part.strip()
                            if clean_part and len(clean_part) > 1 and len(clean_part) < 100:
                                synonyms.append(clean_part)

        # Remove duplicates and clean up
        unique_synonyms = []
        seen = set()
        for syn in synonyms:
            clean_syn = syn.strip()
            if clean_syn and clean_syn.lower() not in seen:
                unique_synonyms.append(clean_syn)
                seen.add(clean_syn.lower())

        return unique_synonyms[:15]  # Limit to top 15 synonyms

    def _extract_chemical_classes(self, soup: BeautifulSoup) -> List[str]:
        """Extract chemical classification from HMDB page."""
        classes = []

        # Look for taxonomy/classification section
        taxonomy_section = soup.find('h2', string=re.compile(r'Chemical Taxonomy', re.I))
        if taxonomy_section:
            next_element = taxonomy_section.find_next(['table', 'div'])
            if next_element:
                class_links = next_element.find_all('a')
                for link in class_links:
                    class_name = link.get_text(strip=True)
                    if class_name and class_name not in classes:
                        classes.append(class_name)

        return classes[:10]  # Limit to top 10 classes

    def _extract_description(self, soup: BeautifulSoup) -> str:
        """Extract metabolite description from HMDB page."""
        # Look for description section
        desc_section = soup.find('h2', string=re.compile(r'Description', re.I))
        if desc_section:
            next_element = desc_section.find_next(['p', 'div'])
            if next_element:
                description = next_element.get_text(strip=True)
                if len(description) > 1000:
                    description = description[:1000] + "..."
                return description
        return ""

    def _extract_iupac_name(self, soup: BeautifulSoup) -> str:
        """Extract IUPAC name from HMDB page."""
        iupac_cells = soup.find_all('td', string=re.compile(r'IUPAC', re.I))
        for cell in iupac_cells:
            next_cell = cell.find_next_sibling('td')
            if next_cell:
                return next_cell.get_text(strip=True)
        return ""

    def _extract_common_name(self, soup: BeautifulSoup) -> str:
        """Extract common name from HMDB page."""
        common_cells = soup.find_all('td', string=re.compile(r'Common Name', re.I))
        for cell in common_cells:
            next_cell = cell.find_next_sibling('td')
            if next_cell:
                return next_cell.get_text(strip=True)
        return ""

    def _extract_taxonomy_field(self, soup: BeautifulSoup, field_name: str) -> str:
        """Extract specific taxonomy field from HMDB page."""
        field_cells = soup.find_all('td', string=re.compile(field_name, re.I))
        for cell in field_cells:
            next_cell = cell.find_next_sibling('td')
            if next_cell:
                return next_cell.get_text(strip=True)
        return ""

    def _create_empty_hmdb_info(self, hmdb_id: str) -> Dict[str, Any]:
        """Create empty HMDB info structure."""
        return {
            'hmdb_id': hmdb_id,
            'synonyms': [],
            'chemical_classes': [],
            'description': '',
            'iupac_name': '',
            'common_name': '',
            'kingdom': '',
            'super_class': '',
            'class': '',
            'sub_class': '',
            'direct_parent': '',
            'source': 'HMDB',
            'timestamp': datetime.now().isoformat(),
            'success': False
        }

    def _determine_primary_source(self, hmdb_info: Dict[str, Any], pubchem_info: Dict[str, Any], perplexity_info: Dict[str, Any]) -> str:
        """
        Determine the primary data source based on the prioritization order: HMDB > PubChem > Perplexity.
        
        Args:
            hmdb_info: Information retrieved from HMDB
            pubchem_info: Information retrieved from PubChem
            perplexity_info: Information retrieved from Perplexity
            
        Returns:
            str: The name of the primary data source
        """
        # Check sources in order of priority
        if hmdb_info.get('success', False):
            return 'HMDB'
        elif pubchem_info.get('success', False):
            return 'PubChem'
        elif perplexity_info.get('success', False):
            return 'Perplexity'
        else:
            return 'None'  # No successful source
    
    def _create_contextual_info(self, metabolite_name: str, hmdb_id: str) -> Dict[str, Any]:
        """Create contextual information for metabolites, especially NOID ones."""
        contextual_info = {
            'enhanced': False,
            'synonyms': [],
            'chemical_class': '',
            'description': '',
            'metabolite_type': ''
        }

        name_lower = metabolite_name.lower()

        # Detect metabolite patterns and add contextual information
        if 'DG(' in metabolite_name or 'diglyceride' in name_lower:
            contextual_info.update({
                'enhanced': True,
                'synonyms': ['Diacylglycerol', 'DAG', '1,2-Diacyl-sn-glycerol'],
                'chemical_class': 'Glycerolipid',
                'description': 'Lipid molecule involved in fat metabolism and cellular signaling pathways.',
                'metabolite_type': 'Diglyceride'
            })
        elif 'PC(' in metabolite_name or 'phosphatidylcholine' in name_lower:
            contextual_info.update({
                'enhanced': True,
                'synonyms': ['PC', 'Lecithin', 'Phosphocholine'],
                'chemical_class': 'Phospholipid',
                'description': 'Major component of cell membranes and involved in lipid transport.',
                'metabolite_type': 'Phosphatidylcholine'
            })
        elif 'TG(' in metabolite_name or 'triglyceride' in name_lower:
            contextual_info.update({
                'enhanced': True,
                'synonyms': ['Triacylglycerol', 'TAG', 'Neutral fat'],
                'chemical_class': 'Triacylglycerol',
                'description': 'Storage form of fat in adipose tissue and major energy reserve.',
                'metabolite_type': 'Triglyceride'
            })
        elif 'ceramide' in name_lower or 'cer(' in metabolite_name:
            contextual_info.update({
                'enhanced': True,
                'synonyms': ['Ceramide', 'N-acylsphingosine'],
                'chemical_class': 'Sphingolipid',
                'description': 'Sphingolipid involved in cell membrane structure and signaling.',
                'metabolite_type': 'Ceramide'
            })
        elif 'carnitine' in name_lower or metabolite_name.startswith('C'):
            contextual_info.update({
                'enhanced': True,
                'synonyms': ['Acylcarnitine', 'Fatty acid carnitine ester'],
                'chemical_class': 'Acylcarnitine',
                'description': 'Fatty acid derivative involved in fatty acid oxidation and energy metabolism.',
                'metabolite_type': 'Acylcarnitine'
            })
        elif any(aa in name_lower for aa in ['leucine', 'glycine', 'alanine', 'valine', 'isoleucine']):
            contextual_info.update({
                'enhanced': True,
                'synonyms': ['Amino acid'],
                'chemical_class': 'Amino acid',
                'description': 'Building block of proteins involved in various metabolic processes.',
                'metabolite_type': 'Amino acid'
            })

        return contextual_info

    def _create_empty_pubchem_info(self) -> Dict[str, Any]:
        """Create empty PubChem info structure."""
        return {
            'pubchem_cid': '',
            'molecular_formula': '',
            'molecular_weight': '',
            'canonical_smiles': '',
            'inchi': '',
            'pubchem_synonyms': [],
            'source': 'PubChem',
            'timestamp': datetime.now().isoformat(),
            'success': False
        }

    def _get_best_value(self, values: List[str]) -> str:
        """Get the best non-empty value from a list of values."""
        for value in values:
            if value and value.strip():
                return value.strip()
        return ''

    def _get_best_chemical_classes(self, hmdb_info: Dict, perplexity_info: Dict) -> List[str]:
        """Get the best chemical classes from available sources."""
        # Prefer Perplexity classes if available
        perplexity_classes = perplexity_info.get('chemical_classes', [])
        if perplexity_classes:
            return perplexity_classes

        # Fallback to HMDB classes
        return hmdb_info.get('chemical_classes', [])

    def _create_enhanced_name(self, original_name: str, hmdb_info: Dict, contextual_info: Dict, perplexity_info: Dict = None) -> str:
        """Create an enhanced name for the metabolite."""
        enhanced_name = original_name

        # Prefer Perplexity common name if available
        if perplexity_info and perplexity_info.get('common_name'):
            enhanced_name = perplexity_info['common_name']
        # Use HMDB common name if available
        elif hmdb_info.get('common_name'):
            enhanced_name = hmdb_info['common_name']

        # Add contextual type if available
        if contextual_info.get('metabolite_type'):
            enhanced_name = f"{original_name} ({contextual_info['metabolite_type']})"

        return enhanced_name

    def _combine_synonyms(self, hmdb_info: Dict, pubchem_info: Dict, contextual_info: Dict, perplexity_info: Dict = None) -> List[str]:
        """Combine synonyms from all sources."""
        all_synonyms = []

        # Add Perplexity synonyms first (highest priority)
        if perplexity_info:
            all_synonyms.extend(perplexity_info.get('synonyms', []))

        # Add HMDB synonyms
        all_synonyms.extend(hmdb_info.get('synonyms', []))

        # Add PubChem synonyms
        all_synonyms.extend(pubchem_info.get('pubchem_synonyms', []))

        # Add contextual synonyms
        all_synonyms.extend(contextual_info.get('synonyms', []))

        # Remove duplicates while preserving order
        unique_synonyms = []
        seen = set()
        for syn in all_synonyms:
            if syn and syn.lower() not in seen:
                unique_synonyms.append(syn)
                seen.add(syn.lower())

        return unique_synonyms[:20]  # Limit to top 20 synonyms

    def _create_llm_description(self, metabolite_name: str, hmdb_info: Dict, contextual_info: Dict, perplexity_info: Dict = None) -> str:
        """Create a comprehensive description for LLM consumption."""
        desc_parts = [f"Metabolite: {metabolite_name}"]

        # Add chemical class (prefer Perplexity)
        chemical_class = ''
        if perplexity_info and perplexity_info.get('chemical_classes'):
            chemical_class = perplexity_info['chemical_classes'][0]
        elif contextual_info.get('chemical_class'):
            chemical_class = contextual_info['chemical_class']
        elif hmdb_info.get('chemical_classes'):
            chemical_class = hmdb_info['chemical_classes'][0]

        if chemical_class:
            desc_parts.append(f"\nChemical class: {chemical_class}")

        # Add synonyms
        synonyms = self._combine_synonyms(hmdb_info, {}, contextual_info, perplexity_info)
        if synonyms:
            desc_parts.append(f"\nAlso known as: {', '.join(synonyms[:3])}")

        # Add description (prefer Perplexity)
        description = ''
        if perplexity_info and perplexity_info.get('description'):
            description = perplexity_info['description']
        elif hmdb_info.get('description'):
            description = hmdb_info['description']
        elif contextual_info.get('description'):
            description = contextual_info['description']

        if description:
            brief_desc = description.split('.')[0] + '.' if '.' in description else description
            if len(brief_desc) > 200:
                brief_desc = brief_desc[:200] + "..."
            desc_parts.append(f"\nDescription: {brief_desc}")

        # Add biological roles if available from Perplexity
        if perplexity_info and perplexity_info.get('biological_roles'):
            roles = perplexity_info['biological_roles'][:2]  # Limit to 2 roles
            desc_parts.append(f"\nBiological roles: {', '.join(roles)}")

        return ' | '.join(desc_parts)

    def process_metabolites_from_csv(self, csv_file: str = "input/normal_ranges.csv",
                                   sample_size: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
        """
        Process metabolites from CSV file and enrich them.

        Args:
            csv_file (str): Path to CSV file
            sample_size (Optional[int]): Limit processing to first N metabolites

        Returns:
            Dict: Enriched metabolite data keyed by HMDB ID
        """
        try:
            # Load CSV
            df = pd.read_csv(csv_file)
            logger.info(f"Loaded {len(df)} metabolites from {csv_file}")

            # Sample if requested
            if sample_size:
                df = df.head(sample_size)
                logger.info(f"Processing sample of {len(df)} metabolites")

            enriched_data = {}
            enriched_data_by_name = {}

            # Process each metabolite
            for idx, row in df.iterrows():
                hmdb_ids_combined = row['hmdb']
                metabolite_name = row['chemical_name']
                
                # Check if the HMDB_ID field contains multiple IDs separated by spaces
                if isinstance(hmdb_ids_combined, str):
                    hmdb_ids = hmdb_ids_combined.split()
                else:
                    # Handle non-string values (like NaN)
                    logger.warning(f"Non-string HMDB_ID value for {metabolite_name}: {hmdb_ids_combined}")
                    continue
                    
                logger.info(f"Processing {metabolite_name} ({hmdb_ids_combined}) [{idx+1}/{len(df)}]")
                
                # Store original CSV data once
                original_data = {
                    'low_level': row.get('low_level', ''),
                    'high_level': row.get('high_level', ''),
                    'sd': row.get('sd', ''),
                    'reference': row.get('reference', '')
                }
                
                # Initialize the by-name entry if it doesn't exist
                if metabolite_name not in enriched_data_by_name:
                    # We'll populate this with the first HMDB ID's data and then just add other HMDB IDs to the list
                    enriched_data_by_name[metabolite_name] = {
                        'metabolite_name': metabolite_name,
                        'hmdb_id_list': [],
                        'original_data': original_data
                    }
                
                # Process each HMDB ID separately
                for hmdb_id in hmdb_ids:
                    logger.debug(f"  - Processing individual HMDB ID: {hmdb_id} for {metabolite_name}")
                    
                    # Enrich metabolite
                    enriched_metabolite = self.enrich_metabolite(hmdb_id, metabolite_name)
                    
                    # Add original CSV data
                    enriched_metabolite['original_data'] = original_data
                    
                    # Store in results dictionary
                    enriched_data[hmdb_id] = enriched_metabolite
                    
                    # Add HMDB ID to the by-name structure's list
                    enriched_data_by_name[metabolite_name]['hmdb_id_list'].append(hmdb_id)
                    
                    # If this is the first HMDB ID for this metabolite, initialize the structure
                    if len(enriched_data_by_name[metabolite_name]['hmdb_id_list']) == 1:
                        # Copy all keys except hmdb_id and original_data (which we've already set)
                        for key, value in enriched_metabolite.items():
                            if key not in ['hmdb_id', 'original_data']:
                                enriched_data_by_name[metabolite_name][key] = value
                        
                        # Initialize timing data structure
                        enriched_data_by_name[metabolite_name]['timing_data'] = {
                            'total_enrichment_seconds': 0,
                            'sources_by_hmdb': {}
                        }
                        
                        # Initialize database_ids structure to store multiple HMDB IDs and their associated data
                        enriched_data_by_name[metabolite_name]['database_ids'] = {
                            'hmdb_ids': {},
                            'pubchem_cids': {}
                        }
                        
                        # Initialize lists for data that we'll merge from multiple HMDB IDs
                        enriched_data_by_name[metabolite_name]['all_sources'] = []
                    
                    # Always add this HMDB ID's source information
                    source_info = {
                        'hmdb_id': hmdb_id,
                        'enhanced_name': enriched_metabolite.get('enhanced_name', metabolite_name),
                        'perplexity_success': enriched_metabolite.get('data_sources', {}).get('perplexity_success', False),
                        'hmdb_success': enriched_metabolite.get('data_sources', {}).get('hmdb_success', False),
                        'pubchem_success': enriched_metabolite.get('data_sources', {}).get('pubchem_success', False),
                        'primary_source': enriched_metabolite.get('data_sources', {}).get('primary_source', '')
                    }
                    
                    # Add timing information if available
                    if 'timing_summary' in enriched_metabolite:
                        source_info['timing'] = enriched_metabolite['timing_summary']
                        
                        # Add to the timing_data structure
                        timing_data = enriched_data_by_name[metabolite_name]['timing_data']
                        timing_data['sources_by_hmdb'][hmdb_id] = enriched_metabolite['timing_summary']
                        
                        # Update total enrichment time
                        timing_data['total_enrichment_seconds'] += enriched_metabolite['timing_summary'].get('total_enrichment_seconds', 0)
                    
                    # Add source info to the list
                    enriched_data_by_name[metabolite_name]['all_sources'].append(source_info)
                    
                    # Store database IDs for this HMDB ID
                    if 'database_ids' in enriched_metabolite:
                        # Store HMDB ID with its associated data
                        enriched_data_by_name[metabolite_name]['database_ids']['hmdb_ids'][hmdb_id] = {
                            'primary': enriched_metabolite['data_sources'].get('primary_source') == 'HMDB',
                            'success': enriched_metabolite['data_sources'].get('hmdb_success', False)
                        }
                        
                        # Store PubChem CID if available
                        pubchem_cid = enriched_metabolite['database_ids'].get('pubchem_cid')
                        if pubchem_cid:
                            enriched_data_by_name[metabolite_name]['database_ids']['pubchem_cids'][pubchem_cid] = {
                                'hmdb_id': hmdb_id,
                                'primary': enriched_metabolite['data_sources'].get('primary_source') == 'PubChem',
                                'success': enriched_metabolite['data_sources'].get('pubchem_success', False)
                            }
                    
                    # Merge synonyms if they exist
                    if 'all_synonyms' in enriched_metabolite and enriched_metabolite['all_synonyms']:
                        current_synonyms = set(enriched_data_by_name[metabolite_name].get('all_synonyms', []))
                        new_synonyms = set(enriched_metabolite['all_synonyms'])
                        enriched_data_by_name[metabolite_name]['all_synonyms'] = list(current_synonyms.union(new_synonyms))
                        
                    # Merge chemical classes if they exist
                    if 'chemical_classes' in enriched_metabolite and enriched_metabolite['chemical_classes']:
                        current_classes = set(enriched_data_by_name[metabolite_name].get('chemical_classes', []))
                        new_classes = set(enriched_metabolite['chemical_classes'])
                        enriched_data_by_name[metabolite_name]['chemical_classes'] = list(current_classes.union(new_classes))
                        
                    # Merge biological roles if they exist
                    if 'biological_roles' in enriched_metabolite and enriched_metabolite['biological_roles']:
                        current_roles = set(enriched_data_by_name[metabolite_name].get('biological_roles', []))
                        new_roles = set(enriched_metabolite['biological_roles'])
                        enriched_data_by_name[metabolite_name]['biological_roles'] = list(current_roles.union(new_roles))
                        
                    # Merge descriptions
                    if 'descriptions' in enriched_metabolite:
                        if 'descriptions' not in enriched_data_by_name[metabolite_name]:
                            enriched_data_by_name[metabolite_name]['descriptions'] = {}
                            
                        # Merge PubChem description if available
                        if enriched_metabolite['descriptions'].get('pubchem_description') and not enriched_data_by_name[metabolite_name]['descriptions'].get('pubchem_description'):
                            enriched_data_by_name[metabolite_name]['descriptions']['pubchem_description'] = enriched_metabolite['descriptions']['pubchem_description']
                            
                        # Merge HMDB description if available
                        if enriched_metabolite['descriptions'].get('hmdb_description') and not enriched_data_by_name[metabolite_name]['descriptions'].get('hmdb_description'):
                            enriched_data_by_name[metabolite_name]['descriptions']['hmdb_description'] = enriched_metabolite['descriptions']['hmdb_description']
                    
                    # Merge chemical properties
                    if 'chemical_properties' in enriched_metabolite:
                        if 'chemical_properties' not in enriched_data_by_name[metabolite_name]:
                            enriched_data_by_name[metabolite_name]['chemical_properties'] = {}
                            
                        properties = enriched_data_by_name[metabolite_name]['chemical_properties']
                        new_properties = enriched_metabolite['chemical_properties']
                        
                        # Fill in missing properties from this HMDB ID
                        for prop_key, prop_value in new_properties.items():
                            if prop_value and not properties.get(prop_key):
                                properties[prop_key] = prop_value
                                
                        # Special handling for literature abstracts - merge them
                        if 'literature_abstracts' in new_properties and new_properties['literature_abstracts']:
                            if 'literature_abstracts' not in properties:
                                properties['literature_abstracts'] = []
                            properties['literature_abstracts'].extend(new_properties['literature_abstracts'])
                    
                    # Merge taxonomy information
                    if 'taxonomy' in enriched_metabolite:
                        if 'taxonomy' not in enriched_data_by_name[metabolite_name]:
                            enriched_data_by_name[metabolite_name]['taxonomy'] = {}
                            
                        taxonomy = enriched_data_by_name[metabolite_name]['taxonomy']
                        new_taxonomy = enriched_metabolite['taxonomy']
                        
                        # Fill in missing taxonomy fields
                        for tax_key, tax_value in new_taxonomy.items():
                            if tax_value and not taxonomy.get(tax_key):
                                taxonomy[tax_key] = tax_value
                                
                    # Merge food recommendations if they exist
                    if 'food_recommendations' in enriched_metabolite:
                        if 'food_recommendations' not in enriched_data_by_name[metabolite_name]:
                            enriched_data_by_name[metabolite_name]['food_recommendations'] = {
                                'avoid_high': [],
                                'consume_high': [],
                                'avoid_low': [],
                                'consume_low': []
                            }
                            
                        food_recs = enriched_data_by_name[metabolite_name]['food_recommendations']
                        new_food_recs = enriched_metabolite['food_recommendations']
                        
                        # Merge each category of food recommendations
                        for category in ['avoid_high', 'consume_high', 'avoid_low', 'consume_low']:
                            if category in new_food_recs and new_food_recs[category]:
                                current_foods = set(food_recs.get(category, []))
                                new_foods = set(new_food_recs[category])
                                food_recs[category] = list(current_foods.union(new_foods))
                                
                    # Merge health conditions if they exist
                    if 'health_conditions' in enriched_metabolite:
                        if 'health_conditions' not in enriched_data_by_name[metabolite_name]:
                            enriched_data_by_name[metabolite_name]['health_conditions'] = {
                                'high_level': [],
                                'low_level': []
                            }
                            
                        health_conds = enriched_data_by_name[metabolite_name]['health_conditions']
                        new_health_conds = enriched_metabolite['health_conditions']
                        
                        # Merge each category of health conditions
                        for category in ['high_level', 'low_level']:
                            if category in new_health_conds and new_health_conds[category]:
                                current_conditions = set(health_conds.get(category, []))
                                new_conditions = set(new_health_conds[category])
                                health_conds[category] = list(current_conditions.union(new_conditions))

                # Save cache periodically
                if (idx + 1) % 10 == 0:
                    self.save_cache()
                    logger.info(f"Processed {idx + 1} metabolites, cache saved")

            # Final cache save
            self.save_cache()

            # Store in instance
            # Post-process the enriched_data_by_name to add summary information
            for metabolite_name, metabolite_data in enriched_data_by_name.items():
                # Create a summary of database IDs
                if 'database_ids' in metabolite_data:
                    # Get the primary HMDB ID (first one that was successful, or just the first one)
                    hmdb_ids = metabolite_data['database_ids']['hmdb_ids']
                    primary_hmdb_id = next(
                        (hmdb_id for hmdb_id, data in hmdb_ids.items() if data.get('primary')),
                        next(iter(hmdb_ids.keys()), '')
                    )
                    
                    # Get the primary PubChem CID
                    pubchem_cids = metabolite_data['database_ids']['pubchem_cids']
                    primary_pubchem_cid = next(
                        (cid for cid, data in pubchem_cids.items() if data.get('primary')),
                        next(iter(pubchem_cids.keys()), '')
                    )
                    
                    # Add a simple summary for backward compatibility
                    metabolite_data['database_ids_summary'] = {
                        'primary_hmdb_id': primary_hmdb_id,
                        'primary_pubchem_cid': primary_pubchem_cid,
                        'hmdb_id_count': len(hmdb_ids),
                        'pubchem_cid_count': len(pubchem_cids)
                    }
            
            self.enriched_data = enriched_data
            self.enriched_data_by_name = enriched_data_by_name

            logger.info(f"Successfully enriched {len(enriched_data)} metabolites for {len(enriched_data_by_name)} unique metabolite names")
            return enriched_data

        except Exception as e:
            logger.error(f"Error processing metabolites from CSV: {e}")
            raise

    def save_enriched_data_to_json(self, output_file=None):
        """Save the enriched data to a JSON file."""
        if output_file is None:
            output_file = 'data/metabolite_enriched_data.json'
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        try:
            with open(output_file, 'w') as f:
                json.dump(self.enriched_data, f, indent=2)
            
            logger.info(f"Saved enriched data for {len(self.enriched_data)} metabolites to {output_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving enriched data to JSON: {e}")
            return False

    def save_enriched_data_by_name_to_json(self, output_file: str = "data/metabolite_enriched_data_by_name.json") -> bool:
        """
        Save enriched data organized by metabolite name to JSON file.

        Args:
            output_file (str): Output JSON file path

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(output_file), exist_ok=True)

            # Create a copy of the data to ensure we don't modify the original
            output_data = copy.deepcopy(self.enriched_data_by_name)

            # Ensure all metabolites have the database_ids and database_ids_summary fields
            for metabolite_name, metabolite_data in output_data.items():
                if 'hmdb_id_list' in metabolite_data and len(metabolite_data['hmdb_id_list']) > 0:
                    # Make sure database_ids structure exists
                    if 'database_ids' not in metabolite_data:
                        metabolite_data['database_ids'] = {
                            'hmdb_ids': {},
                            'pubchem_cids': {}
                        }

                        # Add basic info for each HMDB ID
                        for hmdb_id in metabolite_data['hmdb_id_list']:
                            metabolite_data['database_ids']['hmdb_ids'][hmdb_id] = {
                                'primary': False,
                                'success': True
                            }

                        # Set the first HMDB ID as primary if none is marked
                        if metabolite_data['hmdb_id_list']:
                            first_hmdb_id = metabolite_data['hmdb_id_list'][0]
                            metabolite_data['database_ids']['hmdb_ids'][first_hmdb_id]['primary'] = True

                    # Make sure database_ids_summary exists
                    if 'database_ids_summary' not in metabolite_data:
                        hmdb_ids = metabolite_data['database_ids']['hmdb_ids']
                        pubchem_cids = metabolite_data['database_ids']['pubchem_cids']

                        # Get the primary HMDB ID (first one that was successful, or just the first one)
                        primary_hmdb_id = next(
                            (hmdb_id for hmdb_id, data in hmdb_ids.items() if data.get('primary')),
                            next(iter(hmdb_ids.keys()), '')
                        )

                        # Get the primary PubChem CID
                        primary_pubchem_cid = next(
                            (cid for cid, data in pubchem_cids.items() if data.get('primary')),
                            next(iter(pubchem_cids.keys()), '')
                        )

                        # Add a simple summary
                        metabolite_data['database_ids_summary'] = {
                            'primary_hmdb_id': primary_hmdb_id,
                            'primary_pubchem_cid': primary_pubchem_cid,
                            'hmdb_id_count': len(hmdb_ids),
                            'pubchem_cid_count': len(pubchem_cids)
                        }

            with open(output_file, 'w') as f:
                json.dump(output_data, f, indent=2)

            logger.info(f"Saved enriched data by name for {len(output_data)} metabolites to {output_file}")
            return True

        except Exception as e:
            logger.error(f"Error saving enriched data by name to JSON: {e}")
            return False

    def save_enriched_data_to_csv(self, output_file: str = ENRICHED_CSV_FILE) -> bool:
        """
        Save enriched metabolite data to CSV file for compatibility.

        Args:
            output_file (str): Output CSV file path

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self.enriched_data:
                logger.error("No enriched data to save")
                return False

            # Convert enriched data to DataFrame format
            rows = []
            for hmdb_id, data in self.enriched_data.items():
                row = {
                    'chemical_name': data['original_name'],
                    'hmdb': hmdb_id,
                    'low_level': data['original_data'].get('low_level', ''),
                    'high_level': data['original_data'].get('high_level', ''),
                    'sd': data['original_data'].get('sd', ''),
                    'reference': data['original_data'].get('reference', ''),
                    'enhanced_name': data['enhanced_name'],
                    'synonyms': '; '.join(data['all_synonyms']),
                    'chemical_classes': '; '.join(data['chemical_classes']),
                    'description': data['descriptions']['hmdb_description'],
                    'contextual_description': data['descriptions']['contextual_description'],
                    'llm_description': data['descriptions']['llm_description'],
                    'iupac_name': data['chemical_properties']['iupac_name'],
                    'common_name': data['chemical_properties']['common_name'],
                    'molecular_formula': data['chemical_properties']['molecular_formula'],
                    'molecular_weight': data['chemical_properties']['molecular_weight'],
                    'pubchem_cid': data['database_ids']['pubchem_cid'],
                    'kingdom': data['taxonomy']['kingdom'],
                    'super_class': data['taxonomy']['super_class'],
                    'class': data['taxonomy']['class'],
                    'sub_class': data['taxonomy']['sub_class'],
                    'direct_parent': data['taxonomy']['direct_parent'],
                    'hmdb_success': data['data_sources']['hmdb_success'],
                    'pubchem_success': data['data_sources']['pubchem_success'],
                    'has_contextual_info': data['data_sources']['has_contextual_info'],
                    'enriched_timestamp': data['enrichment_metadata']['enriched_timestamp']
                }
                rows.append(row)

            # Create DataFrame and save
            df = pd.DataFrame(rows)
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(output_file, index=False)

            logger.info(f"Saved enriched data for {len(rows)} metabolites to {output_file}")
            return True

        except Exception as e:
            logger.error(f"Error saving enriched data to CSV: {e}")
            return False

def load_enriched_metabolite_data(json_file: str = ENRICHED_JSON_FILE) -> Dict[str, Dict[str, Any]]:
    """
    Load enriched metabolite data from JSON file.

    Args:
        json_file (str): Path to enriched metabolite JSON file

    Returns:
        Dict: Enriched metabolite data keyed by HMDB ID
    """
    try:
        if not Path(json_file).exists():
            logger.warning(f"Enriched data file not found: {json_file}")
            return {}

        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        logger.info(f"Loaded enriched data for {len(data)} metabolites from {json_file}")
        return data

    except Exception as e:
        logger.error(f"Error loading enriched data: {e}")
        return {}

def get_metabolite_enriched_info(hmdb_id: str, enriched_data: Dict[str, Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Get enriched information for a specific metabolite.

    Args:
        hmdb_id (str): HMDB ID of the metabolite
        enriched_data (Dict, optional): Pre-loaded enriched data

    Returns:
        Dict: Enriched metabolite information or empty dict if not found
    """
    if enriched_data is None:
        enriched_data = load_enriched_metabolite_data()

    return enriched_data.get(hmdb_id, {})

def create_enhanced_prompt_from_enriched_data(
    hmdb_id: str,
    concentration_status: str,
    enriched_data: Dict[str, Dict[str, Any]] = None
) -> str:
    """
    Create an enhanced prompt using enriched metabolite data.

    Args:
        hmdb_id (str): HMDB ID of the metabolite
        concentration_status (str): 'high' or 'low'
        enriched_data (Dict, optional): Pre-loaded enriched data

    Returns:
        str: Enhanced prompt for LLM
    """
    metabolite_info = get_metabolite_enriched_info(hmdb_id, enriched_data)

    if not metabolite_info:
        # Fallback to basic prompt
        return f"Provide dietary advice for managing {concentration_status} levels of metabolite {hmdb_id}."

    # Extract enriched information
    original_name = metabolite_info.get('original_name', '')
    enhanced_name = metabolite_info.get('enhanced_name', original_name)
    llm_description = metabolite_info.get('descriptions', {}).get('llm_description', '')
    synonyms = metabolite_info.get('all_synonyms', [])
    chemical_classes = metabolite_info.get('chemical_classes', [])

    # Build enhanced prompt
    prompt_parts = []

    # Main request
    status_text = "excessive" if concentration_status.lower() == "high" else "insufficient"
    prompt_parts.append(f"Provide specific dietary advice for managing {status_text} levels of the following metabolite:")

    # Enhanced metabolite information
    if llm_description:
        prompt_parts.append(f"\n{llm_description}")
    else:
        prompt_parts.append(f"\nMetabolite: {enhanced_name}")

    # Additional context
    if chemical_classes:
        prompt_parts.append(f"\nChemical classification: {', '.join(chemical_classes[:3])}")

    if synonyms:
        # Add key synonyms for context
        key_synonyms = synonyms[:5]  # Limit to 5 synonyms
        prompt_parts.append(f"\nAlso known as: {', '.join(key_synonyms)}")

    # Specific dietary guidance request with JSON format
    if concentration_status.lower() == "high":
        prompt_parts.append(f"""
Please provide dietary advice in JSON format for managing EXCESSIVE levels of this metabolite:

{{
  "Foods to Decrease/Avoid": [
    "List specific foods, food groups, or dietary components that should be reduced or avoided"
  ],
  "Foods to Increase/Consume": [
    "List specific foods or nutrients that may help reduce levels of this metabolite"
  ],
  "Practical Dietary Strategies": [
    "List practical meal planning tips, cooking methods, or dietary patterns"
  ]
}}

Focus on evidence-based dietary interventions that can help reduce {enhanced_name} levels.""")
    else:
        prompt_parts.append(f"""
Please provide dietary advice in JSON format for managing INSUFFICIENT levels of this metabolite:

{{
  "Foods to Increase/Consume": [
    "List specific foods, food groups, or dietary components that are rich in or promote this metabolite"
  ],
  "Foods to Decrease/Avoid": [
    "List foods or dietary factors that may interfere with absorption or production"
  ],
  "Practical Dietary Strategies": [
    "List practical meal planning tips, cooking methods, or dietary patterns"
  ]
}}

Focus on evidence-based dietary interventions that can help increase {enhanced_name} levels.""")

    return '\n'.join(prompt_parts)

def main():
    """
    Main entry point for the script.
    """
    parser = argparse.ArgumentParser(description="Enrich metabolite data with additional information.")
    parser.add_argument("--input", default="src/input/normal_ranges_with_all_HMDB_IDs.csv", 
                       help="Input CSV file with metabolite data")
    parser.add_argument("--output", default="data/metabolite_enriched_data.json",
                       help="Output JSON file for enriched data")
    parser.add_argument("--output-csv", default="data/enriched_normal_ranges.csv",
                       help="Output CSV file for enriched data")
    parser.add_argument("--use-perplexity", action="store_true", help="Use Perplexity API for enrichment regardless of HMDB/PubChem results")
    parser.add_argument("--refresh-cache", action="store_true", help="Bypass cache for Perplexity API calls")
    parser.add_argument("--force-pubchem", action="store_true", 
                       help="Force PubChem data collection even when Perplexity data is available")
    parser.add_argument('--include-health-conditions', action='store_true', help='Include health conditions associated with high/low metabolite concentrations')
    parser.add_argument('--include-food-recommendations', action='store_true', help='Include food recommendations for high/low metabolite concentrations')
    parser.add_argument("--sample-size", type=int, help="Process only a sample of metabolites")
    parser.add_argument("--cache-file", help="Custom cache file location")

    args = parser.parse_args()

    try:
        # Initialize the enricher
        enricher = MetaboliteDataEnricher(
            cache_file=args.cache_file or CACHE_FILE,
            use_perplexity_first=args.use_perplexity,
            refresh_cache=args.refresh_cache,
            force_pubchem=args.force_pubchem,
            include_health_conditions=args.include_health_conditions,
            include_food_recommendations=args.include_food_recommendations
        )

        # Process metabolites
        enriched_data = enricher.process_metabolites_from_csv(
            csv_file=args.input,
            sample_size=args.sample_size
        )

        # Save to JSON
        if enricher.save_enriched_data_to_json():
            json_output_status = "✓"
        else:
            json_output_status = "✗"
        
        # Save enriched data by name to JSON
        if enricher.save_enriched_data_by_name_to_json():
            json_by_name_output_status = "✓"
        else:
            json_by_name_output_status = "✗"
            
        # Save to CSV for compatibility
        if enricher.save_enriched_data_to_csv():
            csv_output_status = "✓"
        else:
            csv_output_status = "✗"

        # Show summary
        logger.info("Metabolite enrichment completed successfully!")
        logger.info(f"Total metabolites processed: {len(enriched_data)}")
        logger.info(f"JSON output: {json_output_status} {args.output}")
        logger.info(f"JSON by name output: {json_by_name_output_status} data/metabolite_enriched_data_by_name.json")
        logger.info(f"CSV output: {csv_output_status} {args.output_csv}")

        # Show statistics
        perplexity_success = sum(1 for data in enriched_data.values()
                               if data.get('data_sources', {}).get('perplexity_success', False))
        hmdb_success = sum(1 for data in enriched_data.values()
                         if data.get('data_sources', {}).get('hmdb_success', False))
        pubchem_success = sum(1 for data in enriched_data.values()
                            if data.get('data_sources', {}).get('pubchem_success', False))
        contextual_info = sum(1 for data in enriched_data.values()
                            if data.get('data_sources', {}).get('has_contextual_info', False))

        logger.info(f"Perplexity enrichment success: {perplexity_success} ({perplexity_success/len(enriched_data)*100:.1f}%)")
        logger.info(f"HMDB enrichment success: {hmdb_success} ({hmdb_success/len(enriched_data)*100:.1f}%)")
        logger.info(f"PubChem enrichment success: {pubchem_success} ({pubchem_success/len(enriched_data)*100:.1f}%)")
        logger.info(f"Contextual enrichment: {contextual_info} ({contextual_info/len(enriched_data)*100:.1f}%)")

        # Show primary source distribution
        perplexity_primary = sum(1 for data in enriched_data.values()
                               if data.get('data_sources', {}).get('primary_source') == 'perplexity')
        hmdb_primary = sum(1 for data in enriched_data.values()
                         if data.get('data_sources', {}).get('primary_source') == 'hmdb')

        logger.info(f"Primary source - Perplexity: {perplexity_primary} ({perplexity_primary/len(enriched_data)*100:.1f}%)")
        logger.info(f"Primary source - HMDB: {hmdb_primary} ({hmdb_primary/len(enriched_data)*100:.1f}%)")

        return 0

    except Exception as e:
        logger.error(f"Error during enrichment: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
