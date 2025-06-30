#!/usr/bin/env python3
"""
Find HMDB ID conflicts between enrichment data and advice files.

This script identifies cases where:
1. A single HMDB ID from enrichment data matches multiple entries in advice files
2. Multiple metabolites in enrichment data share the same HMDB ID
3. Potential duplicate or conflicting entries that need resolution
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Any, Tuple
from datetime import datetime
from collections import defaultdict


def load_json_file(file_path: str) -> Dict[str, Any]:
    """Load JSON file safely."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: File not found: {file_path}")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {file_path}: {e}")
        return {}


def extract_individual_hmdb_ids(hmdb_ids_raw: List[str]) -> List[str]:
    """Extract individual HMDB IDs from space-separated strings."""
    if not hmdb_ids_raw or not hmdb_ids_raw[0]:
        return []

    # Split space-separated HMDB IDs and trim whitespace
    if ' ' in hmdb_ids_raw[0]:
        individual_ids = [id_str.strip() for id_str in hmdb_ids_raw[0].split() if id_str.strip()]
    else:
        individual_ids = [hmdb_ids_raw[0].strip()]

    return individual_ids


def analyze_hmdb_conflicts(enrichment_file: str, high_advice_file: str, low_advice_file: str) -> Dict[str, Any]:
    """Analyze HMDB ID conflicts between enrichment and advice data."""

    print(f"Loading enrichment data from: {enrichment_file}")
    enrichment_data = load_json_file(enrichment_file)

    print(f"Loading high concentration advice from: {high_advice_file}")
    high_advice = load_json_file(high_advice_file)

    print(f"Loading low concentration advice from: {low_advice_file}")
    low_advice = load_json_file(low_advice_file)

    print(f"\nLoaded {len(enrichment_data)} metabolites from enrichment data")
    print(f"Loaded {len(high_advice)} entries from high concentration advice")
    print(f"Loaded {len(low_advice)} entries from low concentration advice")

    # Build reverse mapping: HMDB ID -> list of metabolites that have this ID
    enrichment_hmdb_to_metabolites = defaultdict(list)
    advice_hmdb_to_metabolites = defaultdict(list)

    print(f"\nBuilding HMDB ID mappings...")

    # Process enrichment data
    for metabolite_name, metabolite_data in enrichment_data.items():
        hmdb_ids = metabolite_data.get('hmdb_ids', [])
        individual_ids = extract_individual_hmdb_ids(hmdb_ids)

        for hmdb_id in individual_ids:
            enrichment_hmdb_to_metabolites[hmdb_id].append({
                'metabolite_name': metabolite_name,
                'all_hmdb_ids': individual_ids,
                'synonyms': metabolite_data.get('synonyms', []),
                'categories': metabolite_data.get('categories', [])
            })

    # Process advice data (combine high and low)
    all_advice = {}
    all_advice.update({k: {'source': 'high', **v} for k, v in high_advice.items()})
    all_advice.update({k: {'source': 'low', **v} for k, v in low_advice.items()})

    for hmdb_id, advice_data in all_advice.items():
        advice_hmdb_to_metabolites[hmdb_id].append({
            'metabolite_name': advice_data.get('metabolite', 'Unknown'),
            'source_file': advice_data['source'],
            'hmdb_id': hmdb_id
        })

    # Find conflicts
    conflicts = {
        'enrichment_multiple_metabolites_same_hmdb': {},  # One HMDB ID -> multiple enrichment metabolites
        'advice_multiple_entries_same_hmdb': {},          # One HMDB ID -> multiple advice entries
        'cross_file_conflicts': {},                       # HMDB ID conflicts between enrichment and advice
        'potential_duplicates': {}                        # Metabolites that might be duplicates
    }

    print(f"Analyzing conflicts...")

    # 1. Find enrichment metabolites sharing HMDB IDs
    for hmdb_id, metabolites in enrichment_hmdb_to_metabolites.items():
        if len(metabolites) > 1:
            conflicts['enrichment_multiple_metabolites_same_hmdb'][hmdb_id] = {
                'hmdb_id': hmdb_id,
                'metabolite_count': len(metabolites),
                'metabolites': metabolites
            }

    # 2. Find advice entries sharing HMDB IDs (shouldn't happen but check)
    for hmdb_id, entries in advice_hmdb_to_metabolites.items():
        if len(entries) > 1:
            conflicts['advice_multiple_entries_same_hmdb'][hmdb_id] = {
                'hmdb_id': hmdb_id,
                'entry_count': len(entries),
                'entries': entries
            }

    # 3. Find cross-file conflicts (enrichment HMDB ID matches multiple advice entries)
    for hmdb_id in enrichment_hmdb_to_metabolites:
        if hmdb_id in advice_hmdb_to_metabolites:
            enrichment_metabolites = enrichment_hmdb_to_metabolites[hmdb_id]
            advice_entries = advice_hmdb_to_metabolites[hmdb_id]

            # Check if there are multiple matches or name mismatches
            if len(enrichment_metabolites) > 1 or len(advice_entries) > 1:
                conflicts['cross_file_conflicts'][hmdb_id] = {
                    'hmdb_id': hmdb_id,
                    'enrichment_metabolites': enrichment_metabolites,
                    'advice_entries': advice_entries,
                    'conflict_type': 'multiple_matches'
                }
            else:
                # Check for name mismatches
                enrich_name = enrichment_metabolites[0]['metabolite_name']
                advice_name = advice_entries[0]['metabolite_name']
                if enrich_name != advice_name:
                    conflicts['cross_file_conflicts'][hmdb_id] = {
                        'hmdb_id': hmdb_id,
                        'enrichment_metabolites': enrichment_metabolites,
                        'advice_entries': advice_entries,
                        'conflict_type': 'name_mismatch'
                    }

    # 4. Find potential duplicates (same metabolite name with different HMDB IDs)
    metabolite_name_to_hmdb_ids = defaultdict(set)
    for hmdb_id, metabolites in enrichment_hmdb_to_metabolites.items():
        for metabolite_info in metabolites:
            metabolite_name_to_hmdb_ids[metabolite_info['metabolite_name']].add(hmdb_id)

    for metabolite_name, hmdb_ids in metabolite_name_to_hmdb_ids.items():
        if len(hmdb_ids) > 1:
            conflicts['potential_duplicates'][metabolite_name] = {
                'metabolite_name': metabolite_name,
                'hmdb_ids': list(hmdb_ids),
                'hmdb_count': len(hmdb_ids)
            }

    # Compile results
    results = {
        'analysis_metadata': {
            'timestamp': datetime.now().isoformat(),
            'enrichment_file': enrichment_file,
            'high_advice_file': high_advice_file,
            'low_advice_file': low_advice_file,
            'total_enrichment_metabolites': len(enrichment_data),
            'total_advice_entries': len(all_advice),
            'unique_enrichment_hmdb_ids': len(enrichment_hmdb_to_metabolites),
            'unique_advice_hmdb_ids': len(advice_hmdb_to_metabolites),
            'enrichment_conflicts_count': len(conflicts['enrichment_multiple_metabolites_same_hmdb']),
            'advice_conflicts_count': len(conflicts['advice_multiple_entries_same_hmdb']),
            'cross_file_conflicts_count': len(conflicts['cross_file_conflicts']),
            'potential_duplicates_count': len(conflicts['potential_duplicates'])
        },
        'conflicts': conflicts
    }

    return results


def create_advice_multiple_matches_report(results: Dict[str, Any], output_file: str):
    """Create a focused report on advice entries that match multiple enrichment metabolites."""

    conflicts = results['conflicts']
    cross_file_conflicts = conflicts['cross_file_conflicts']

    # Find advice entries that match multiple enrichment metabolites
    advice_multiple_matches = {}

    for hmdb_id, conflict in cross_file_conflicts.items():
        if conflict['conflict_type'] == 'multiple_matches':
            enrichment_metabolites = conflict['enrichment_metabolites']
            advice_entries = conflict['advice_entries']

            # Focus on cases where one advice entry matches multiple enrichment metabolites
            if len(enrichment_metabolites) > 1:
                for advice_entry in advice_entries:
                    advice_metabolite = advice_entry['metabolite_name']
                    advice_key = f"{advice_entry['hmdb_id']}_{advice_metabolite}"

                    advice_multiple_matches[advice_key] = {
                        'advice_metabolite_name': advice_metabolite,
                        'advice_hmdb_id': advice_entry['hmdb_id'],
                        'advice_source_file': advice_entry['source_file'],
                        'matching_enrichment_metabolites': enrichment_metabolites,
                        'enrichment_metabolite_count': len(enrichment_metabolites),
                        'potential_issue': 'One advice entry matches multiple enrichment metabolites'
                    }

    # Create focused report
    focused_report = {
        'report_metadata': {
            'timestamp': datetime.now().isoformat(),
            'report_type': 'advice_multiple_matches',
            'description': 'Advice entries that have HMDB IDs matching multiple metabolites in enrichment data',
            'total_conflicts': len(advice_multiple_matches)
        },
        'advice_entries_with_multiple_enrichment_matches': advice_multiple_matches
    }

    # Save focused report
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(focused_report, f, indent=2, ensure_ascii=False)

    print(f"\nFocused report created: {output_file}")
    print(f"Advice entries with multiple enrichment matches: {len(advice_multiple_matches)}")

    return focused_report


def main():
    parser = argparse.ArgumentParser(
        description="Find HMDB ID conflicts between enrichment and advice data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze conflicts with default files
  python src/find_hmdb_conflicts.py

  # Create focused report on advice multiple matches
  python src/find_hmdb_conflicts.py --create-focused-report

  # Specify custom output file
  python src/find_hmdb_conflicts.py --output hmdb_conflicts_analysis.json

  # Use custom advice files
  python src/find_hmdb_conflicts.py --high-advice custom_high.json --low-advice custom_low.json
        """
    )

    parser.add_argument(
        '--enrichment-file',
        default='perplexity_only_sonar/perplexity_only_sonar_sonar_perplexity_only_synonyms_categories.json',
        help='Path to enrichment data file'
    )

    parser.add_argument(
        '--high-advice',
        default='src/input/metabolite_info_high.json',
        help='Path to high concentration advice file'
    )

    parser.add_argument(
        '--low-advice',
        default='src/input/metabolite_info_low.json',
        help='Path to low concentration advice file'
    )

    parser.add_argument(
        '--output',
        default='hmdb_conflicts_analysis.json',
        help='Output file for conflict analysis'
    )

    parser.add_argument(
        '--create-focused-report',
        action='store_true',
        help='Create focused report on advice entries with multiple enrichment matches'
    )

    parser.add_argument(
        '--focused-output',
        default='advice_multiple_matches.json',
        help='Output file for focused report'
    )

    args = parser.parse_args()

    # Perform analysis
    results = analyze_hmdb_conflicts(
        args.enrichment_file,
        args.high_advice,
        args.low_advice
    )

    # Save results
    output_path = Path(args.output)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Create focused report if requested
    if args.create_focused_report:
        focused_report = create_advice_multiple_matches_report(results, args.focused_output)

    # Print summary
    metadata = results["analysis_metadata"]
    conflicts = results["conflicts"]

    print(f"\n" + "="*60)
    print("HMDB ID CONFLICT ANALYSIS SUMMARY")
    print("="*60)
    print(f"Total enrichment metabolites: {metadata['total_enrichment_metabolites']}")
    print(f"Total advice entries: {metadata['total_advice_entries']}")
    print(f"Unique enrichment HMDB IDs: {metadata['unique_enrichment_hmdb_ids']}")
    print(f"Unique advice HMDB IDs: {metadata['unique_advice_hmdb_ids']}")
    print()
    print("CONFLICT BREAKDOWN:")
    print(f"Enrichment: Multiple metabolites sharing HMDB ID: {metadata['enrichment_conflicts_count']}")
    print(f"Advice: Multiple entries sharing HMDB ID: {metadata['advice_conflicts_count']}")
    print(f"Cross-file: HMDB ID conflicts between files: {metadata['cross_file_conflicts_count']}")
    print(f"Potential duplicates: Same name, different HMDB IDs: {metadata['potential_duplicates_count']}")
    print()

    # Show examples if conflicts exist
    if metadata['enrichment_conflicts_count'] > 0:
        print("ENRICHMENT CONFLICTS (first 3):")
        count = 0
        for hmdb_id, conflict in conflicts['enrichment_multiple_metabolites_same_hmdb'].items():
            metabolite_names = [m['metabolite_name'] for m in conflict['metabolites']]
            print(f"  {hmdb_id}: {metabolite_names}")
            count += 1
            if count >= 3:
                break
        print()

    if metadata['cross_file_conflicts_count'] > 0:
        print("CROSS-FILE CONFLICTS (first 3):")
        count = 0
        for hmdb_id, conflict in conflicts['cross_file_conflicts'].items():
            enrich_names = [m['metabolite_name'] for m in conflict['enrichment_metabolites']]
            advice_names = [e['metabolite_name'] for e in conflict['advice_entries']]
            print(f"  {hmdb_id}: Enrichment={enrich_names}, Advice={advice_names}")
            count += 1
            if count >= 3:
                break
        print()

    print(f"Analysis saved to: {output_path.absolute()}")
    print("="*60)


if __name__ == "__main__":
    main()
