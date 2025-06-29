#!/usr/bin/env python3
"""
Script to implement and test the improved PubChem lookup method.
"""

import os
import sys
import json
import time
import logging
import requests
from datetime import datetime
from typing import Dict, Any, List
from urllib.parse import quote

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
RATE_LIMIT_DELAY = 0.5  # seconds between API calls to avoid rate limiting

class PubChemLookup:
    """
    Class for looking up metabolite information in PubChem.
    """
    
    def __init__(self):
        """Initialize the PubChemLookup."""
        self.cache = {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'MetaboliteDataEnricher/1.0 (research project; contact@example.com)'
        })
    
    def get_pubchem_info(self, metabolite_name: str, hmdb_id: str = "") -> Dict[str, Any]:
        """
        Get additional information from PubChem API.

        Args:
            metabolite_name (str): Name of the metabolite
            hmdb_id (str): HMDB ID for the metabolite

        Returns:
            Dict containing additional chemical information
        """
        # Start timing
        start_time = time.time()
        
        cache_key = f"pubchem_{hmdb_id}_{metabolite_name}"
        if cache_key in self.cache:
            logger.debug(f"Using cached PubChem data for {metabolite_name} (HMDB ID: {hmdb_id})")
            result = self.cache[cache_key]
            return result

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
                    logger.debug(f"PubChem HMDB ID search successful for {hmdb_id}")
                except Exception as hmdb_search_error:
                    logger.warning(f"Failed to find {metabolite_name} (HMDB ID: {hmdb_id}) in PubChem by HMDB ID, falling back to name search: {hmdb_search_error}")
            
            # If HMDB ID search failed or wasn't available, try by name
            if data is None:
                try:
                    search_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{quote(metabolite_name)}/JSON"
                    logger.info(f"Searching PubChem by name: {metabolite_name}")
                    response = self.session.get(search_url, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    logger.debug(f"PubChem name search successful for {metabolite_name}")
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

                # Extract properties
                if 'props' in compound:
                    for prop in compound['props']:
                        if 'urn' in prop and 'label' in prop['urn']:
                            label = prop['urn']['label']
                            if label == 'Molecular Formula' and 'value' in prop:
                                info['molecular_formula'] = prop['value']['sval']
                            elif label == 'Molecular Weight' and 'value' in prop:
                                if 'fval' in prop['value']:
                                    info['molecular_weight'] = str(prop['value']['fval'])
                                elif 'sval' in prop['value']:
                                    info['molecular_weight'] = str(prop['value']['sval'])
                            elif label == 'SMILES' and 'value' in prop:
                                info['canonical_smiles'] = prop['value']['sval']
                            elif label == 'InChI' and 'value' in prop:
                                info['inchi'] = prop['value']['sval']

            # Calculate time taken
            end_time = time.time()
            elapsed_time = end_time - start_time
            
            # Add timing information
            info['timing'] = {
                'source': 'pubchem',
                'elapsed_seconds': round(elapsed_time, 2),
                'from_cache': False
            }
            
            logger.debug(f"PubChem fetch took {elapsed_time:.2f} seconds for {metabolite_name}")
            
            # Cache the result
            self.cache[cache_key] = info

            # Rate limiting
            time.sleep(RATE_LIMIT_DELAY)
            
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

def test_pubchem_lookup():
    """Test the improved PubChem lookup method with sample metabolites."""
    # Sample metabolites with HMDB IDs
    test_metabolites = [
        {"name": "Butyric acid", "hmdb_id": "HMDB0000039"},
        {"name": "L-Glutamic acid", "hmdb_id": "HMDB0000148"},
        {"name": "Glucose", "hmdb_id": "HMDB0000122"},
        {"name": "Cholesterol", "hmdb_id": "HMDB0000067"},
        {"name": "Urea", "hmdb_id": "HMDB0000294"}
    ]
    
    # Initialize the PubChem lookup
    pubchem_lookup = PubChemLookup()
    
    # Test results
    results = []
    
    # Run tests
    for metabolite in test_metabolites:
        name = metabolite["name"]
        hmdb_id = metabolite["hmdb_id"]
        
        logger.info(f"Testing PubChem lookup for {name} (HMDB ID: {hmdb_id})")
        
        # Test with HMDB ID
        info_with_hmdb = pubchem_lookup.get_pubchem_info(name, hmdb_id)
        
        # Test without HMDB ID (name-based lookup only)
        info_without_hmdb = pubchem_lookup.get_pubchem_info(name)
        
        # Compare results
        results.append({
            "metabolite_name": name,
            "hmdb_id": hmdb_id,
            "with_hmdb_id": {
                "success": info_with_hmdb.get("success", False),
                "pubchem_cid": info_with_hmdb.get("pubchem_cid", ""),
                "molecular_formula": info_with_hmdb.get("molecular_formula", "")
            },
            "without_hmdb_id": {
                "success": info_without_hmdb.get("success", False),
                "pubchem_cid": info_without_hmdb.get("pubchem_cid", ""),
                "molecular_formula": info_without_hmdb.get("molecular_formula", "")
            },
            "same_result": info_with_hmdb.get("pubchem_cid", "") == info_without_hmdb.get("pubchem_cid", "")
        })
    
    # Print results
    print("\nTest Results:")
    print("============")
    
    success_count = 0
    for result in results:
        print(f"\nMetabolite: {result['metabolite_name']} (HMDB ID: {result['hmdb_id']})")
        print(f"With HMDB ID: Success={result['with_hmdb_id']['success']}, CID={result['with_hmdb_id']['pubchem_cid']}")
        print(f"Without HMDB ID: Success={result['without_hmdb_id']['success']}, CID={result['without_hmdb_id']['pubchem_cid']}")
        print(f"Same result: {result['same_result']}")
        
        if result['with_hmdb_id']['success']:
            success_count += 1
    
    print(f"\nOverall success rate: {success_count}/{len(test_metabolites)} ({success_count/len(test_metabolites)*100:.1f}%)")
    
    # Save results to file
    output_file = "improved_pubchem_lookup_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nDetailed results saved to {output_file}")

if __name__ == "__main__":
    test_pubchem_lookup()
