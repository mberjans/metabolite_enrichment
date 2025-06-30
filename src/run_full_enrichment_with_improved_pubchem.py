#!/usr/bin/env python3

import argparse
import logging
import os
import sys
from pathlib import Path

from metabolite_data_enricher import MetaboliteDataEnricher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description='Run metabolite data enrichment with improved PubChem parsing')
    parser.add_argument('--input', type=str, help='Input CSV file with metabolite data (required for batch mode)')
    parser.add_argument('--output-dir', type=str, default='output', help='Output directory for enriched data')
    parser.add_argument('--single-metabolite', type=str, help='Process only a single metabolite by name')
    parser.add_argument('--limit', type=int, help='Limit the number of metabolites to process')
    parser.add_argument('--cache-dir', type=str, default='cache', help='Directory for caching API responses')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.single_metabolite and not args.input:
        parser.error('Either --single-metabolite or --input must be provided')

    # Create output and cache directories
    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(args.cache_dir, exist_ok=True)

    # Initialize enricher
    enricher = MetaboliteDataEnricher(
        cache_file=os.path.join(args.cache_dir, 'enricher_cache.pkl')
    )
    
    # Set output directory
    enricher.output_dir = args.output_dir

    try:
        if args.single_metabolite:
            # Single metabolite mode
            logger.info(f"Processing single metabolite: {args.single_metabolite}")
            result = enricher.process_single_metabolite(args.single_metabolite)
            if result:
                logger.info(f"Successfully processed {args.single_metabolite}")
            else:
                logger.error(f"Failed to process {args.single_metabolite}")
        else:
            # Batch mode
            logger.info(f"Processing metabolites from {args.input}")
            enricher.process_metabolites_from_csv(
                args.input,
                sample_size=args.limit
            )
            # Save enriched data to combined JSON files in the specified output directory
            enricher.save_enriched_data_to_json(os.path.join(args.output_dir, 'metabolite_enriched_data.json'))
            enricher.save_enriched_data_by_name_to_json(os.path.join(args.output_dir, 'metabolite_enriched_data_by_name.json'))
            logger.info("Enrichment process completed")

    except Exception as e:
        logger.error(f"Error during enrichment process: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
