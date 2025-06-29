# Script Merger: Creating a Unified Metabolite Enrichment Pipeline

This document outlines the process of merging `run_full_enrichment_with_improved_pubchem.py` and our optimized HMDB XML parsing functionality into a unified script called `run_full_enrichment_with_improved_pubchem_and_hmdb.py`.

## Objective

Create a unified script that:
1. Uses the optimized HMDB XML parsing as the primary method for HMDB data extraction
2. Falls back to the original HMDB HTML parsing when XML is not available
3. Preserves all existing PubChem functionality from `run_full_enrichment_with_improved_pubchem.py`
4. Maintains all other features of the original script

## Implementation Steps

### 1. Create the Unified Script

Create a new file `run_full_enrichment_with_improved_pubchem_and_hmdb.py` based on `run_full_enrichment_with_improved_pubchem.py`.

### 2. Import Required Modules

Add imports for the optimized HMDB XML parsing:

```python
import os
import re
import time
import json
import logging
import argparse
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Import both HMDB lookup classes
from src.enhanced_hmdb_lookup import EnhancedHMDBLookup as OriginalHMDBLookup
from src.enhanced_hmdb_lookup_optimized import EnhancedHMDBLookup as OptimizedHMDBLookup

# Import existing modules
from src.pubchem_lookup import PubChemLookup
from src.openrouter_lookup import OpenRouterLookup
```

### 3. Create a Combined HMDB Lookup Class

Create a new class that combines both HMDB lookup approaches:

```python
class CombinedHMDBLookup:
    """
    Combined HMDB lookup class that uses optimized XML parsing as primary method
    and falls back to original HTML parsing when XML is not available.
    """
    
    def __init__(self, csv_file: str = 'src/input/normal_ranges_with_all_HMDB_IDs.csv', download_always: bool = False):
        """
        Initialize the CombinedHMDBLookup.
        
        Args:
            csv_file: Path to CSV file with metabolite name to HMDB ID mapping
            download_always: Whether to always download fresh XML data
        """
        self.optimized_lookup = OptimizedHMDBLookup(csv_file, download_always)
        self.original_lookup = OriginalHMDBLookup(csv_file)
        self.logger = logging.getLogger(__name__)
    
    def get_hmdb_info(self, hmdb_id: str, metabolite_name: str) -> Dict[str, Any]:
        """
        Get HMDB information using optimized XML parsing first, then fall back to original HTML parsing.
        
        Args:
            hmdb_id: HMDB ID or semicolon-separated list of HMDB IDs
            metabolite_name: Name of the metabolite
            
        Returns:
            Dictionary containing HMDB information
        """
        try:
            # Try optimized XML parsing first
            self.logger.info(f"Attempting to get HMDB info for {metabolite_name} using optimized XML parsing")
            result = self.optimized_lookup.get_hmdb_info(hmdb_id, metabolite_name)
            
            # Check if we got meaningful data
            if result and result.get('synonyms') and len(result.get('synonyms', [])) > 0:
                self.logger.info(f"Successfully retrieved HMDB data using optimized XML parsing")
                return result
            else:
                self.logger.info(f"Optimized XML parsing returned incomplete data, falling back to original method")
        except Exception as e:
            self.logger.warning(f"Error in optimized XML parsing: {str(e)}, falling back to original method")
        
        # Fall back to original HTML parsing
        self.logger.info(f"Attempting to get HMDB info for {metabolite_name} using original HTML parsing")
        return self.original_lookup.get_hmdb_info(hmdb_id, metabolite_name)
```

### 4. Update the Enrichment Function

Modify the `enrich_metabolite` function to use the combined HMDB lookup:

```python
def enrich_metabolite(metabolite_name: str, hmdb_id: str, download_always: bool = False) -> Dict[str, Any]:
    """
    Enrich a metabolite with data from HMDB, PubChem, and OpenRouter.
    
    Args:
        metabolite_name: Name of the metabolite
        hmdb_id: HMDB ID or semicolon-separated list of HMDB IDs
        download_always: Whether to always download fresh HMDB XML data
        
    Returns:
        Dictionary containing enriched metabolite data
    """
    start_time = time.time()
    logger.info(f"Enriching metabolite: {metabolite_name}")
    
    # Initialize result dictionary
    result = {
        "name": metabolite_name,
        "hmdb_id": hmdb_id,
        "synonyms": [],
        "description": "",
        "kingdom": "",
        "super_class": "",
        "class": "",
        "sub_class": "",
        "direct_parent": "",
        "iupac_name": "",
        "timing": {
            "total_seconds": 0.0,
            "hmdb_seconds": 0.0,
            "pubchem_seconds": 0.0,
            "openrouter_seconds": 0.0
        }
    }
    
    try:
        # Get HMDB data using combined lookup
        hmdb_lookup = CombinedHMDBLookup(download_always=download_always)
        hmdb_info = hmdb_lookup.get_hmdb_info(hmdb_id, metabolite_name)
        
        # Update result with HMDB data
        if hmdb_info:
            result["hmdb_id"] = hmdb_info.get("hmdb_id", hmdb_id)
            result["synonyms"].extend(hmdb_info.get("synonyms", []))
            result["description"] = hmdb_info.get("description", "")
            result["kingdom"] = hmdb_info.get("kingdom", "")
            result["super_class"] = hmdb_info.get("super_class", "")
            result["class"] = hmdb_info.get("class", "")
            result["sub_class"] = hmdb_info.get("sub_class", "")
            result["direct_parent"] = hmdb_info.get("direct_parent", "")
            result["iupac_name"] = hmdb_info.get("iupac_name", "")
            
            # Add timing information
            if "timing" in hmdb_info:
                result["timing"]["hmdb_seconds"] = hmdb_info["timing"].get("elapsed_seconds", 0.0)
        
        # Continue with existing PubChem and OpenRouter functionality...
        # [Keep the rest of the function as is]
        
    except Exception as e:
        logger.error(f"Error enriching metabolite {metabolite_name}: {str(e)}")
    
    # Calculate total time
    elapsed_time = time.time() - start_time
    result["timing"]["total_seconds"] = elapsed_time
    logger.info(f"Enrichment completed in {elapsed_time:.2f} seconds for {metabolite_name}")
    
    return result
```

### 5. Update the Main Function

Modify the main function to include the new command-line argument for HMDB XML downloading:

```python
def main():
    """Main function to process metabolite file and enrich data."""
    parser = argparse.ArgumentParser(description="Enrich metabolite data with HMDB and PubChem information")
    parser.add_argument("--input", "-i", default="src/input/normal_ranges_with_all_HMDB_IDs.csv",
                        help="Path to input CSV file with metabolite data")
    parser.add_argument("--output", "-o", default="data/enriched_metabolites.json",
                        help="Path to output JSON file for enriched data")
    parser.add_argument("--limit", "-l", type=int, help="Limit number of metabolites to process")
    parser.add_argument("--download_HMDB_XML_always", "-d", action="store_true",
                        help="Always download fresh HMDB XML files instead of using local versions")
    parser.add_argument("--output_by_hmdb", action="store_true",
                        help="Generate additional output file with HMDB IDs as keys")
    parser.add_argument("--output_by_name", action="store_true",
                        help="Generate additional output file with metabolite names as keys")
    
    args = parser.parse_args()
    
    # Create output directory if it doesn't exist
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Process the metabolite file
    process_metabolite_file(args.input, args.output, args.limit, 
                           download_always=args.download_HMDB_XML_always,
                           output_by_hmdb=args.output_by_hmdb,
                           output_by_name=args.output_by_name)
```

### 6. Update the Process Metabolite File Function

Modify the `process_metabolite_file` function to support additional output formats:

```python
def process_metabolite_file(input_file: str, output_file: str, limit: Optional[int] = None, 
                           download_always: bool = False, output_by_hmdb: bool = False,
                           output_by_name: bool = False):
    """
    Process a file containing metabolite information and enrich each metabolite.
    
    Args:
        input_file: Path to input CSV file
        output_file: Path to output JSON file
        limit: Optional limit on number of metabolites to process
        download_always: Whether to always download fresh HMDB XML data
        output_by_hmdb: Whether to generate additional output with HMDB IDs as keys
        output_by_name: Whether to generate additional output with metabolite names as keys
    """
    # [Keep the existing function implementation]
    
    # Add code to generate additional output formats
    if output_by_hmdb:
        hmdb_output = {}
        for result in results:
            hmdb_id = result.get("hmdb_id", "")
            if hmdb_id:
                hmdb_output[hmdb_id] = result
        
        hmdb_output_file = output_file.replace(".json", "_by_hmdb.json")
        with open(hmdb_output_file, "w") as f:
            json.dump(hmdb_output, f, indent=2)
        logger.info(f"Wrote {len(hmdb_output)} entries to {hmdb_output_file}")
    
    if output_by_name:
        name_output = {}
        for result in results:
            name = result.get("name", "")
            if name:
                name_output[name] = result
        
        name_output_file = output_file.replace(".json", "_by_name.json")
        with open(name_output_file, "w") as f:
            json.dump(name_output, f, indent=2)
        logger.info(f"Wrote {len(name_output)} entries to {name_output_file}")
```

## Testing the Unified Script

After creating the unified script, test it with various scenarios:

1. Basic functionality:
   ```
   python run_full_enrichment_with_improved_pubchem_and_hmdb.py --limit 5
   ```

2. With XML download flag:
   ```
   python run_full_enrichment_with_improved_pubchem_and_hmdb.py --limit 5 --download_HMDB_XML_always
   ```

3. With additional output formats:
   ```
   python run_full_enrichment_with_improved_pubchem_and_hmdb.py --limit 5 --output_by_hmdb --output_by_name
   ```

4. Full run:
   ```
   python run_full_enrichment_with_improved_pubchem_and_hmdb.py
   ```

## Conclusion

This unified script combines the best of both implementations:

1. Uses optimized HMDB XML parsing as the primary method for more complete data
2. Falls back to the original HTML parsing when XML is not available
3. Preserves all existing PubChem functionality
4. Adds support for multiple output formats
5. Maintains all other features of the original script

The result is a robust metabolite enrichment pipeline that maximizes data quality and availability.
