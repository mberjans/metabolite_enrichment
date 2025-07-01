#!/usr/bin/env python3
"""
PubChem Data Retriever Module

This module provides functionality to retrieve compound information from PubChem,
cache the data in JSON format, and parse it for use in enrichment processes.
"""

import logging
import os
import json
import time
from typing import Dict, Any, List, Optional
from urllib.parse import quote
import requests
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
PUBCHEM_CACHE_DIR = 'data/pubchem_cache'
RATE_LIMIT_DELAY = 0.5  # seconds between API calls to avoid rate limiting

# Headers for HTTP requests
HEADERS = {
    'User-Agent': 'MetaboliteDataEnricher/1.0 (research project; contact@example.com)'
}

class PubChemRetriever:
    """
    Class for retrieving and caching PubChem data.
    """
    
    def __init__(self):
        """Initialize the PubChemRetriever."""
        self.cache = {}
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        # Create cache directory
        os.makedirs(PUBCHEM_CACHE_DIR, exist_ok=True)
    
    def _get_cache_path(self, cid: str) -> str:
        """Get the file path for cached PubChem data."""
        return os.path.join(PUBCHEM_CACHE_DIR, f"pubchem_{cid}.json")
    
    def _load_from_cache(self, cid: str) -> Optional[Dict[str, Any]]:
        """Load PubChem data from cache if available."""
        cache_path = self._get_cache_path(cid)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"Loaded cached PubChem data for CID {cid}")
                return data
            except Exception as e:
                logger.error(f"Error loading cached data for CID {cid}: {e}")
                return None
        return None
    
    def _save_to_cache(self, cid: str, data: Dict[str, Any]) -> bool:
        """Save PubChem data to cache."""
        cache_path = self._get_cache_path(cid)
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved PubChem data to cache for CID {cid}")
            return True
        except Exception as e:
            logger.error(f"Error saving data to cache for CID {cid}: {e}")
            return False
    
    def _fetch_pubchem_data(self, cid: str) -> Dict[str, Any]:
        """Fetch PubChem data from API."""
        try:
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"
            logger.info(f"Fetching PubChem data for CID {cid}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            self._save_to_cache(cid, data)
            time.sleep(RATE_LIMIT_DELAY)
            return data
        except Exception as e:
            logger.error(f"Error fetching PubChem data for CID {cid}: {e}")
            return {}
    
    def get_compound_description(self, cid: str) -> Dict[str, Any]:
        """
        Get compound description and properties from PubChem.
        
        Args:
            cid (str): PubChem Compound ID
            
        Returns:
            Dict[str, Any]: Dictionary containing description and properties
        """
        data = self._load_from_cache(cid)
        if not data:
            data = self._fetch_pubchem_data(cid)
        
        if not data or 'Record' not in data:
            logger.warning(f"No valid data found for CID {cid}")
            return {'description': '', 'properties': {}}
        
        description = ""
        properties = {}
        
        if 'Section' in data['Record']:
            for section in data['Record']['Section']:
                if section.get('TOCHeading') == 'Names and Identifiers':
                    description = self._extract_any_text_from_section(section)
                elif section.get('TOCHeading') == 'Chemical and Physical Properties':
                    for subsection in section.get('Section', []):
                        if subsection.get('TOCHeading') == 'Computed Properties':
                            for info in subsection.get('Information', []):
                                if 'Name' in info and 'Value' in info:
                                    if info['Name'] == 'Molecular Weight':
                                        properties['molecular_weight'] = info['Value'].get('String', '')
                                    elif info['Name'] == 'Molecular Formula':
                                        properties['molecular_formula'] = info['Value'].get('String', '')
        
        return {
            'description': description,
            'properties': properties
        }
    
    def get_compound_classifications(self, cid: str) -> Dict[str, Any]:
        """
        Get compound classifications and taxonomy from PubChem.
        
        Args:
            cid (str): PubChem Compound ID
            
        Returns:
            Dict[str, Any]: Dictionary containing classifications and taxonomy
        """
        data = self._load_from_cache(cid)
        if not data:
            data = self._fetch_pubchem_data(cid)
        
        if not data or 'Record' not in data:
            logger.warning(f"No valid data found for CID {cid}")
            return {'classifications': {}, 'taxonomy': {}}
        
        classifications = {}
        taxonomy = {}
        
        if 'Section' in data['Record']:
            for section in data['Record']['Section']:
                if section.get('TOCHeading') == 'Chemical Taxonomy':
                    for subsection in section.get('Section', []):
                        if subsection.get('TOCHeading') == 'Classification':
                            for info in subsection.get('Information', []):
                                if 'Name' in info and 'Value' in info:
                                    if info['Name'] == 'Kingdom':
                                        taxonomy['kingdom'] = info['Value'].get('String', '')
                                    elif info['Name'] == 'Super Class':
                                        classifications['superclass'] = info['Value'].get('String', '')
                                    elif info['Name'] == 'Class':
                                        classifications['class'] = info['Value'].get('String', '')
        
        return {
            'classifications': classifications,
            'taxonomy': taxonomy
        }
    
    def get_compound_bioactivity(self, cid: str) -> Dict[str, Any]:
        """
        Get compound bioactivity data from PubChem.
        
        Args:
            cid (str): PubChem Compound ID
            
        Returns:
            Dict[str, Any]: Dictionary containing bioactivity data
        """
        data = self._load_from_cache(cid)
        if not data:
            data = self._fetch_pubchem_data(cid)
        
        if not data or 'Record' not in data:
            logger.warning(f"No valid data found for CID {cid}")
            return {'bioactivity': []}
        
        bioactivity = []
        
        if 'Section' in data['Record']:
            for section in data['Record']['Section']:
                if section.get('TOCHeading') == 'Biological Test Results':
                    bioactivity_text = self._extract_any_text_from_section(section)
                    if bioactivity_text:
                        bioactivity.append(bioactivity_text)
        
        return {
            'bioactivity': bioactivity
        }
    
    def get_compound_literature(self, cid: str) -> Dict[str, Any]:
        """
        Get compound literature data from PubChem.
        
        Args:
            cid (str): PubChem Compound ID
            
        Returns:
            Dict[str, Any]: Dictionary containing literature data
        """
        data = self._load_from_cache(cid)
        if not data:
            data = self._fetch_pubchem_data(cid)
        
        if not data or 'Record' not in data:
            logger.warning(f"No valid data found for CID {cid}")
            return {'literature': []}
        
        literature = []
        
        if 'Section' in data['Record']:
            for section in data['Record']['Section']:
                if section.get('TOCHeading') == 'Literature':
                    literature_data = self._extract_pubchem_literature_enhanced(section)
                    if literature_data:
                        literature.extend(literature_data)
        
        return {
            'literature': literature[:5]  # Limit to 5 entries
        }
    
    def get_compound_synonyms(self, cid: str) -> Dict[str, Any]:
        """
        Get compound synonyms from PubChem.
        
        Args:
            cid (str): PubChem Compound ID
            
        Returns:
            Dict[str, Any]: Dictionary containing synonyms
        """
        data = self._load_from_cache(cid)
        if not data:
            data = self._fetch_pubchem_data(cid)
        
        if not data or 'Record' not in data:
            logger.warning(f"No valid data found for CID {cid}")
            return {'synonyms': []}
        
        synonyms = []
        
        if 'Section' in data['Record']:
            for section in data['Record']['Section']:
                if section.get('TOCHeading') == 'Names and Identifiers':
                    for subsection in section.get('Section', []):
                        if subsection.get('TOCHeading') == 'Synonyms':
                            for subsubsection in subsection.get('Section', []):
                                if subsubsection.get('TOCHeading') in ['MeSH Synonyms', 'Depositor-Supplied Synonyms']:
                                    for info in subsubsection.get('Information', []):
                                        if 'Value' in info and 'StringWithMarkup' in info['Value']:
                                            for markup in info['Value']['StringWithMarkup']:
                                                if 'String' in markup:
                                                    synonyms.append(markup['String'])
                                        elif 'Value' in info and 'String' in info['Value']:
                                            synonyms.append(info['Value']['String'])
        
        # Clean up synonyms and remove duplicates
        cleaned_synonyms = []
        seen = set()
        for syn in synonyms:
            cleaned = syn.strip()
            if cleaned and cleaned.lower() not in seen and len(cleaned) < 100:
                cleaned_synonyms.append(cleaned)
                seen.add(cleaned.lower())
        
        logger.info(f"Extracted {len(cleaned_synonyms)} unique synonyms from PubChem for CID {cid}")
        return {
            'synonyms': cleaned_synonyms[:20]  # Limit to top 20 synonyms
        }
    
    def _extract_any_text_from_section(self, section: Dict) -> str:
        """
        Extract any text content from a PubChem PUG-View section.
        
        Args:
            section (Dict): Section data from PUG-View
            
        Returns:
            str: Extracted text content
        """
        result = ""
        
        if 'Information' in section:
            for info in section['Information']:
                if 'Value' in info and 'StringWithMarkup' in info['Value']:
                    for markup in info['Value']['StringWithMarkup']:
                        if 'String' in markup:
                            result += markup['String'] + " "
        
        if 'Section' in section:
            for subsection in section['Section']:
                subsection_text = self._extract_any_text_from_section(subsection)
                if subsection_text:
                    result += subsection_text
        
        return result.strip()
    
    def _extract_pubchem_literature_enhanced(self, section: Dict) -> List[Dict[str, str]]:
        """
        Extract literature abstracts from PubChem PUG-View data (enhanced).
        
        Args:
            section (Dict): Literature section data from PUG-View
            
        Returns:
            List[Dict[str, str]]: List of abstracts with title, authors, journal, and text
        """
        abstracts = []
        
        if 'Section' in section:
            for subsection in section['Section']:
                subsection_name = subsection.get('TOCHeading', '')
                
                if subsection_name in ['Consolidated References', 'NLM Curated PubMed Citations', 
                                     'Springer Nature References', 'Thieme References', 'Wiley References']:
                    
                    if 'Information' in subsection:
                        for info in subsection['Information']:
                            abstract = {}
                            
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
                            
                            if 'Value' in info:
                                if 'StringWithMarkup' in info['Value']:
                                    for markup in info['Value']['StringWithMarkup']:
                                        if 'String' in markup:
                                            if not abstract.get('abstract'):
                                                abstract['abstract'] = markup['String']
                                            else:
                                                abstract['abstract'] += " " + markup['String']
                                
                                elif 'String' in info['Value']:
                                    if not abstract.get('abstract'):
                                        abstract['abstract'] = info['Value']['String']
                            
                            if 'Name' in info and not abstract.get('title'):
                                abstract['title'] = info['Name']
                            
                            if abstract.get('title') or abstract.get('abstract') or abstract.get('pubmed_id'):
                                abstracts.append(abstract)
                                
                            if len(abstracts) >= 10:
                                break
                
                if len(abstracts) >= 10:
                    break
        
        return abstracts
    
    def get_compound_data(self, cid: str) -> Dict[str, Any]:
        """
        Get comprehensive compound data from PubChem by combining all available information.
        
        Args:
            cid (str): PubChem Compound ID
            
        Returns:
            Dict[str, Any]: Comprehensive dictionary of compound data
        """
        description_data = self.get_compound_description(cid)
        classifications_data = self.get_compound_classifications(cid)
        bioactivity_data = self.get_compound_bioactivity(cid)
        literature_data = self.get_compound_literature(cid)
        synonyms_data = self.get_compound_synonyms(cid)
        
        return {
            'description': description_data.get('description', ''),
            'properties': description_data.get('properties', {}),
            'classifications': classifications_data.get('classifications', {}),
            'taxonomy': classifications_data.get('taxonomy', {}),
            'bioactivity': bioactivity_data.get('bioactivity', []),
            'literature': literature_data.get('literature', []),
            'synonyms': synonyms_data.get('synonyms', [])
        }

def get_compound_description(cid: str) -> Dict[str, Any]:
    """Wrapper function for backward compatibility."""
    retriever = PubChemRetriever()
    return retriever.get_compound_description(cid)

def get_compound_classifications(cid: str) -> Dict[str, Any]:
    """Wrapper function for backward compatibility."""
    retriever = PubChemRetriever()
    return retriever.get_compound_classifications(cid)

def get_compound_bioactivity(cid: str) -> Dict[str, Any]:
    """Wrapper function for backward compatibility."""
    retriever = PubChemRetriever()
    return retriever.get_compound_bioactivity(cid)

def get_compound_literature(cid: str) -> Dict[str, Any]:
    """Wrapper function for backward compatibility."""
    retriever = PubChemRetriever()
    return retriever.get_compound_literature(cid)

def get_compound_synonyms(cid: str) -> Dict[str, Any]:
    """Wrapper function for backward compatibility."""
    retriever = PubChemRetriever()
    return retriever.get_compound_synonyms(cid)
