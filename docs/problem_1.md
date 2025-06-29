# Metabolite Enrichment Pipeline: HMDB and PubChem Integration Issues

## Problem Overview

The metabolite enrichment pipeline has been experiencing issues with retrieving comprehensive data from HMDB (Human Metabolome Database) and PubChem. We've been working to improve the data retrieval methods, particularly focusing on enhancing PubChem lookups by prioritizing HMDB ID-based searches.

## Key Issues Identified

### 1. PubChem Lookup Method Issues

- The original PubChem lookup method was using an incorrect endpoint for HMDB ID-based searches (`/rest/pug/substance/sourceid/{hmdb_id}/JSON` instead of `/rest/pug/compound/xref/RegistryID/{hmdb_id}/JSON`)
- The method was not properly prioritizing HMDB ID lookups before falling back to name-based searches
- There was inadequate error handling and logging for PubChem API requests

### 2. Multiple HMDB IDs Handling

- Analysis revealed that metabolites with multiple HMDB IDs have a significantly higher failure rate (89.57%) compared to those with single HMDB IDs (44.42%)
- The current implementation doesn't properly try all available HMDB IDs for a metabolite when looking up data

### 3. NOID vs Real HMDB IDs

- Many metabolites have placeholder "NOID" identifiers (e.g., NOID00000) instead of real HMDB IDs
- Some metabolites show NOID identifiers in enriched data but have real HMDB IDs in the CSV file
- 100% of metabolites with NOID identifiers fail to retrieve HMDB data

### 4. Data Structure and Coverage Analysis Issues

- There's a discrepancy in our analysis showing 99.90% HMDB success rate but 0% coverage for HMDB-derived fields (descriptions, synonyms, chemical classes)
- This suggests potential issues with how data is being stored or how our analysis script is checking for HMDB data

### 5. Input File Selection

- We initially used `normal_ranges.csv` instead of `normal_ranges_with_all_HMDB_IDs.csv`, missing the opportunity to leverage multiple HMDB IDs per metabolite

## Solutions Implemented

### 1. Improved PubChem Lookup Method

- Updated the `get_pubchem_info` method to use the correct PubChem REST API endpoint for HMDB ID lookups (`/rest/pug/compound/xref/RegistryID/{hmdb_id}/JSON`)
- Implemented a prioritization strategy: try HMDB ID lookup first, then fall back to name-based search
- Added detailed logging and error handling for PubChem requests
- Implemented caching and rate limiting to prevent redundant API calls

### 2. Testing and Validation

- Created test datasets with metabolites having HMDB IDs but no PubChem data
- Developed test scripts to verify the improved method's effectiveness
- Achieved 100% success rate in PubChem data retrieval on test datasets

### 3. Full Enrichment Script Updates

- Created `run_full_enrichment_with_improved_pubchem.py` to run the full enrichment process with the improved method
- Updated the script to use the correct CSV file with multiple HMDB IDs
- Added functionality to compare before/after PubChem data coverage
- Fixed parameter mismatches in method calls

### 4. Analysis Tools

- Developed `analyze_hmdb_failures.py` to identify root causes of HMDB data retrieval failures
- Created `check_hmdb_coverage.py` to analyze HMDB data coverage in enriched output files
- These tools helped identify the impact of multiple HMDB IDs on data retrieval success

## Recommended Next Steps

### 1. Enhance Multiple HMDB IDs Handling

```python
def get_hmdb_info(self, hmdb_id):
    """
    Get information from HMDB for a given HMDB ID.
    If multiple HMDB IDs are provided (space-separated), try each one until successful.
    """
    # Handle multiple HMDB IDs
    if ' ' in hmdb_id:
        hmdb_ids = hmdb_id.split()
        for single_id in hmdb_ids:
            result = self.get_hmdb_info(single_id)
            if result.get('success'):
                return result
        # If all failed, return the last failure result
        return result
    
    # Rest of the existing method for single HMDB ID...
```

### 2. Fix NOID to HMDB ID Mapping

- Update the enrichment process to properly use real HMDB IDs from the CSV file instead of placeholder NOID identifiers
- Implement a mapping system to translate between NOID identifiers and real HMDB IDs when available

### 3. Investigate Data Structure Discrepancy

- Examine the structure of the regenerated JSON file to understand why HMDB-derived fields show 0% coverage despite high success rate
- Update analysis scripts to correctly identify and count HMDB-derived data in the current format

### 4. Automated Testing Framework

- Develop regression tests to prevent future method signature mismatches
- Create automated tests to verify data coverage and quality after enrichment

### 5. Enhanced Logging and Monitoring

- Implement more detailed logging of API usage and success rates
- Add monitoring for rate limits and errors in production

## Technical Details

### Key Dependencies and APIs

- PubChem REST API endpoints:
  - HMDB ID to PubChem CID lookup: `/rest/pug/compound/xref/RegistryID/{hmdb_id}/JSON`
  - Name-based compound search: `/rest/pug/compound/name/{name}/JSON`
- Python libraries: `requests`, `pandas`, `json`, `logging`, `datetime`, `time`
- Input files: `src/input/normal_ranges_with_all_HMDB_IDs.csv`
- Output files: `data/metabolite_enriched_data.json`, `data/metabolite_enriched_data_by_name.json`

### Environment and Security

- The OpenRouter API key is loaded from `.env` for Perplexity fallback
- No changes to environment variables or security settings required for these improvements

## Conclusion

The primary focus should be on properly handling multiple HMDB IDs and fixing the mapping between NOID identifiers and real HMDB IDs. These improvements will maximize data coverage and accuracy in the metabolite enrichment pipeline.
