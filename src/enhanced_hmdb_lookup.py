"""
Enhanced HMDB lookup wrapper class for metabolite data enrichment.
"""

import logging
import os
import re
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup
from metabolite_hmdb_lookup import (
    get_hmdb_id_from_name,
    get_metabolite_name_from_hmdb_id,
    get_metabolite_info_by_hmdb_id,
    get_diet_advice_by_hmdb_id
)

logger = logging.getLogger(__name__)

# Constants
HMDB_XML_DIR = 'data/hmdb_xml'
HMDB_CACHE_DIR = 'data/hmdb_cache'
HMDB_BASE_URL = 'https://hmdb.ca/metabolites'

class EnhancedHMDBLookup:
    """Wrapper class for HMDB lookup functionality with XML support."""

    def __init__(self, csv_file: str = "src/input/normal_ranges_with_all_HMDB_IDs.csv"):
        self.csv_file = csv_file
        self.cache: Dict[str, Any] = {}
        
        # Create necessary directories
        os.makedirs(HMDB_XML_DIR, exist_ok=True)
        os.makedirs(HMDB_CACHE_DIR, exist_ok=True)
        
        # Set up session for downloads
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Metabolite Research Tool) AppleWebKit/537.36'
        })

    def get_hmdb_id(self, metabolite_name: str) -> Optional[str]:
        """Get HMDB ID for a metabolite name."""
        return get_hmdb_id_from_name(metabolite_name, self.csv_file)

    def get_metabolite_name(self, hmdb_id: str) -> Optional[str]:
        """Get metabolite name for an HMDB ID."""
        return get_metabolite_name_from_hmdb_id(hmdb_id, self.csv_file)

    def get_hmdb_info(self, hmdb_id: str) -> Dict[str, Any]:
        """
        Get comprehensive metabolite information by HMDB ID.
        First checks local XML file, downloads if not present.
        """
        try:
            # Initialize result with success flag
            result = {
                'hmdb_success': False
            }
            
            # First get basic info from CSV
            basic_info = get_metabolite_info_by_hmdb_id(hmdb_id, self.csv_file)
            if basic_info:
                result.update(basic_info)
            
            # Then enrich with XML data
            xml_info = self._get_hmdb_xml_info(hmdb_id)
            if xml_info:
                result.update(xml_info)
                result['hmdb_success'] = True
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting metabolite info for {hmdb_id}: {e}")
            return {'hmdb_success': False}

    def get_diet_advice(self, hmdb_id: str, status: str) -> Dict[str, Any]:
        """Get diet advice by HMDB ID and status."""
        return get_diet_advice_by_hmdb_id(hmdb_id, status)

    def _get_hmdb_xml_info(self, hmdb_id: str) -> Dict[str, Any]:
        """
        Get metabolite information from HMDB XML file.
        Downloads XML if not present locally.
        """
        try:
            xml_path = self._get_hmdb_xml_path(hmdb_id)
            
            # Download XML if not present
            if not os.path.exists(xml_path):
                if not self._download_hmdb_xml(hmdb_id):
                    return {}
            
            # Parse XML and extract information
            return self._parse_hmdb_xml(xml_path)
            
        except Exception as e:
            logger.error(f"Error getting HMDB XML info for {hmdb_id}: {e}")
            return {}

    def _get_hmdb_xml_path(self, hmdb_id: str) -> str:
        """Get path to HMDB XML file for given ID."""
        return os.path.join(HMDB_XML_DIR, f"{hmdb_id}_raw.xml")

    def _download_hmdb_xml(self, hmdb_id: str) -> bool:
        """
        Download HMDB XML file for given ID.
        Returns True if successful, False otherwise.
        """
        try:
            xml_url = f"{HMDB_BASE_URL}/{hmdb_id}.xml"
            response = self.session.get(xml_url)
            response.raise_for_status()
            
            xml_path = self._get_hmdb_xml_path(hmdb_id)
            with open(xml_path, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"Downloaded HMDB XML for {hmdb_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error downloading HMDB XML for {hmdb_id}: {e}")
            return False

    def _parse_hmdb_xml(self, xml_path: str) -> Dict[str, Any]:
        """Parse HMDB XML file and extract relevant information."""
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # Extract basic information
            info = {
                'description': self._get_xml_text(root, './/description'),
                'synonyms': self._filter_chemical_synonyms(self._get_xml_list(root, './/synonyms/synonym')),
                'chemical_formula': self._get_xml_text(root, './/chemical_formula'),
                'average_molecular_weight': self._get_xml_text(root, './/average_molecular_weight'),
                'monisotopic_molecular_weight': self._get_xml_text(root, './/monisotopic_molecular_weight'),
                'iupac_name': self._get_xml_text(root, './/iupac_name'),
                'traditional_iupac': self._get_xml_text(root, './/traditional_iupac'),
                'cas_registry_number': self._get_xml_text(root, './/cas_registry_number'),
                'smiles': self._get_xml_text(root, './/smiles'),
                'inchi': self._get_xml_text(root, './/inchi'),
                'inchikey': self._get_xml_text(root, './/inchikey'),
                'state': self._get_xml_text(root, './/state'),
                'taxonomy': {
                    'description': self._get_xml_text(root, './/taxonomy/description'),
                    'direct_parent': self._get_xml_text(root, './/taxonomy/direct_parent'),
                    'kingdom': self._get_xml_text(root, './/taxonomy/kingdom'),
                    'super_class': self._get_xml_text(root, './/taxonomy/super_class'),
                    'class': self._get_xml_text(root, './/taxonomy/class'),
                    'sub_class': self._get_xml_text(root, './/taxonomy/sub_class'),
                    'molecular_framework': self._get_xml_text(root, './/taxonomy/molecular_framework')
                },
                'biological_properties': {
                    'cellular_locations': self._get_xml_list(root, './/cellular_locations/cellular'),
                    'biospecimen_locations': self._get_xml_list(root, './/biospecimen_locations/biospecimen'),
                    'tissue_locations': self._get_xml_list(root, './/tissue_locations/tissue'),
                    'pathways': self._get_xml_list(root, './/pathways/pathway/name')
                },
                # Extract chemical classes from taxonomy
                'chemical_classes': []
            }
            
            # Build chemical classes from taxonomy
            taxonomy = info.get('taxonomy', {})
            for class_type in ['direct_parent', 'sub_class', 'class', 'super_class', 'kingdom']:
                if class_type in taxonomy and taxonomy[class_type]:
                    info['chemical_classes'].append(taxonomy[class_type])
            
            # Clean up empty values
            info = {k: v for k, v in info.items() if v}
            if 'taxonomy' in info and not any(info['taxonomy'].values()):
                del info['taxonomy']
            if 'biological_properties' in info and not any(info['biological_properties'].values()):
                del info['biological_properties']
            if 'chemical_classes' in info and not info['chemical_classes']:
                del info['chemical_classes']
            
            return info
            
        except Exception as e:
            logger.error(f"Error parsing HMDB XML {xml_path}: {e}")
            return {}

    def _get_xml_text(self, root: ET.Element, xpath: str) -> str:
        """Get text content of first matching XML element."""
        try:
            element = root.find(xpath)
            return element.text.strip() if element is not None and element.text else ""
        except Exception:
            return ""

    def _get_xml_list(self, root: ET.Element, xpath: str) -> List[str]:
        """Get list of text content from matching XML elements."""
        try:
            elements = root.findall(xpath)
            return [e.text.strip() for e in elements if e.text]
        except Exception:
            return []

    def _filter_chemical_synonyms(self, synonyms: List[str]) -> List[str]:
        """
        Filter out non-chemical terms from synonym list.
        
        Args:
            synonyms: List of potential synonyms to filter
        
        Returns:
            List of filtered chemical synonyms
        """
        if not synonyms:
            return []
        
        filtered = []
        
        # Skip patterns that indicate non-synonym content
        skip_patterns = {
            # Taxonomic terms
            'flora', 'fauna', 'kingdom', 'class', 'family', 'species', 'genus',
            'gramineae', 'papilionoideae', 'legume', 'soy', 'cucurbits', 'gourds',
            # Medical/biological terms
            'disease', 'leukaemia', 'digestion', 'stool', 'fecal', 'faecal', 'faeces',
            'cytoplasm', 'cytoplasma', 'cell', 'tissue', 'organ', 'enzyme', 'protein',
            # General descriptive terms
            'extract', 'powder', 'liquid', 'solution', 'mixture', 'derivative',
            'sample', 'preparation', 'fraction', 'component',
            # Locations/sources
            'plant', 'animal', 'human', 'bacterial', 'fungal', 'tissue', 'blood', 'urine',
            'serum', 'plasma', 'saliva', 'cerebrospinal', 'csf',
            # Process terms
            'metabolism', 'synthesis', 'degradation', 'pathway', 'cycle',
            # Biological roles/effects
            'inhibitor', 'activator', 'substrate', 'cofactor', 'vitamin',
            'hormone', 'neurotransmitter', 'receptor', 'enzyme'
        }
        
        # Look for patterns that suggest a chemical name
        chemical_patterns = [
            r'\d+,\d+-',  # e.g., 1,3-
            r'-\w+ane\b',  # e.g., -ethane, -propane
            r'-\w+ene\b',  # e.g., -ethene, -propene
            r'-\w+ol\b',   # e.g., -ethanol, -propanol
            r'-\w+one\b',  # e.g., -ethanone, -propanone
            r'-\w+acid\b', # e.g., -acetic acid
            r'-\w+amine\b', # e.g., -ethylamine
            r'\([A-Z]\d+\)', # e.g., (C4)
            r'[A-Z]\d+[A-Z]\d+', # e.g., C6H12
            r'\b[A-Z][a-z]?\d*\b', # Chemical symbols
            r'alpha-|beta-|gamma-|delta-', # Greek letter prefixes
            r'\bcis-|\btrans-|\bmeta-|\bpara-|\bortho-' # Chemical prefixes
        ]
        
        for syn in synonyms:
            if not syn or len(syn) < 2 or len(syn) > 100:
                continue
                
            # Skip if contains unwanted patterns
            if any(pattern in syn.lower() for pattern in skip_patterns):
                continue
                
            # Accept if it looks like a chemical name or doesn't match any exclusion patterns
            if any(re.search(pattern, syn) for pattern in chemical_patterns) or not any(pattern in syn.lower() for pattern in skip_patterns):
                filtered.append(syn)
        
        return filtered[:20]  # Limit to top 20 synonyms
