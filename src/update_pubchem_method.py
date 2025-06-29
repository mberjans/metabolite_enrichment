#!/usr/bin/env python3
"""
Script to update the get_pubchem_info method in metabolite_data_enricher.py
"""

import os
import re
import sys
import shutil

def update_pubchem_method():
    """Update the get_pubchem_info method in metabolite_data_enricher.py"""
    # File paths
    original_file = "src/metabolite_data_enricher.py"
    backup_file = "src/metabolite_data_enricher.py.bak"
    
    # Create backup
    shutil.copy2(original_file, backup_file)
    print(f"Created backup at {backup_file}")
    
    # Read the original file
    with open(original_file, 'r') as f:
        content = f.read()
    
    # Define the improved method
    improved_method = '''    def get_pubchem_info(self, metabolite_name: str, hmdb_id: str = "") -> Dict[str, Any]:
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
                    return result'''
    
    # Define the pattern to match the existing get_pubchem_info method
    pattern = r'    def get_pubchem_info\(self, metabolite_name: str, hmdb_id: str = ""\) -> Dict\[str, Any\]:(.*?)    def _fetch_pubchem_additional_data'
    
    # Replace the method
    updated_content = re.sub(pattern, improved_method + '\n\n    def _fetch_pubchem_additional_data', content, flags=re.DOTALL)
    
    # Write the updated content back to the file
    with open(original_file, 'w') as f:
        f.write(updated_content)
    
    print(f"Updated get_pubchem_info method in {original_file}")

if __name__ == "__main__":
    update_pubchem_method()
