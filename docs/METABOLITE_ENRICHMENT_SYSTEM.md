# 🧬 Metabolite Enrichment System

## Overview

The Metabolite Enrichment System enhances the metabolite report generator by enriching the basic metabolite information with comprehensive data from HMDB (Human Metabolome Database) and PubChem. This dramatically improves the quality of LLM-generated diet advice by providing richer context and more descriptive metabolite information.

## 🎯 Problem Solved

**Before Enrichment:**
- LLMs receive minimal metabolite information (just name + HMDB ID)
- Technical names like "DG(17:0_17:1)" are not descriptive for diet advice
- Missing synonyms, chemical classes, and biological context
- 405 metabolites (74%) lack any dietary guidance

**After Enrichment:**
- LLMs receive comprehensive metabolite profiles with synonyms, classes, and descriptions
- Enhanced prompts with biological context and chemical classifications
- Structured JSON output format for consistent advice
- Complete coverage for all 545 metabolites in the system

## 🏗️ System Architecture

```
normal_ranges.csv (545 metabolites)
    ↓
metabolite_enrichment.py
    ↓ (HMDB + PubChem APIs)
enriched_normal_ranges.csv
    ↓
update_diet_advice_with_enriched_data.py
    ↓ (Enhanced LLM prompts)
metabolite_info_high.json + metabolite_info_low.json
    ↓
Enhanced Diet Reports
```

## 📊 Data Sources

### 1. **HMDB (Human Metabolome Database)**
- **252 HMDB metabolites** with official IDs
- Synonyms, chemical classifications, descriptions
- IUPAC names and common names
- Biological roles and pathways

### 2. **PubChem**
- Additional chemical information
- Molecular formulas and weights
- Alternative synonyms and identifiers
- Cross-references to other databases

### 3. **NOID Metabolites**
- **292 custom metabolites** without official HMDB IDs
- Complex lipids (diglycerides, phosphatidylcholines, triglycerides)
- Contextual descriptions based on chemical patterns

## 🔧 Core Components

### 1. `metabolite_enrichment.py`
**Main enrichment script that:**
- Scrapes HMDB metabolite pages for detailed information
- Queries PubChem API for additional chemical data
- Creates enhanced metabolite names and LLM-friendly descriptions
- Caches results to avoid repeated API calls
- Outputs enriched CSV with 10+ new columns

**Key Features:**
- Rate limiting to respect API limits
- Robust error handling and fallback mechanisms
- Incremental processing with progress tracking
- Comprehensive caching system

### 2. `update_diet_advice_with_enriched_data.py`
**Enhanced diet advice generator that:**
- Uses enriched metabolite information for better LLM prompts
- Creates concentration-specific prompts (high vs low)
- Requests structured JSON output format
- Integrates with existing diet advice pipeline
- Supports multiple processing modes

### 3. `demo_metabolite_enrichment.py`
**Demonstration script that:**
- Shows before/after prompt comparisons
- Demonstrates enrichment benefits
- Provides sample metabolite examples
- Guides implementation steps

## 📈 Enrichment Results

### Enhanced Metabolite Information
```csv
Original Columns:
- chemical_name, hmdb, low_level, high_level, sd, reference

New Enriched Columns:
- synonyms (up to 15 alternative names)
- chemical_classes (metabolite classifications)
- description (biological function and role)
- iupac_name (systematic chemical name)
- common_name_hmdb (HMDB common name)
- pubchem_cid (PubChem compound ID)
- molecular_formula (chemical formula)
- molecular_weight (molecular weight)
- enhanced_name (LLM-friendly name)
- llm_description (comprehensive description for LLMs)
```

### Example Enrichment
**Before:**
```
Metabolite: DG(17:0_17:1)
HMDB ID: NOID00000
```

**After:**
```
Enhanced Name: DG(17:0_17:1) (Diglyceride)
Synonyms: Diacylglycerol; DAG; 1,2-Diacyl-sn-glycerol
Chemical Class: Glycerolipid
Description: Lipid molecule involved in fat metabolism and cellular signaling pathways. Functions as a second messenger in cellular processes.
LLM Description: Metabolite: DG(17:0_17:1) (Diglyceride) | Chemical class: Glycerolipid | Also known as: Diacylglycerol, DAG | Description: Lipid molecule involved in fat metabolism and cellular signaling.
```

## 🚀 Usage Instructions

### Step 1: Install Dependencies
```bash
pip install beautifulsoup4 lxml requests pandas
```

### Step 2: Test with Sample Data
```bash
# Demonstrate the enrichment system
python src/demo_metabolite_enrichment.py --show-benefits

# Test enrichment with 10 metabolites
python src/metabolite_enrichment.py --sample-size 10 --dry-run
python src/metabolite_enrichment.py --sample-size 10
```

### Step 3: Full Enrichment (30-45 minutes)
```bash
# Enrich all 545 metabolites
python src/metabolite_enrichment.py
```

### Step 4: Generate Enhanced Diet Advice
```bash
# Test with 5 metabolites
python src/update_diet_advice_with_enriched_data.py --sample-size 5

# Generate advice for all missing metabolites
python src/update_diet_advice_with_enriched_data.py --mode add_new
```

## 📋 Command Line Options

### `metabolite_enrichment.py`
```bash
--input              Input CSV file (default: input/normal_ranges.csv)
--output             Output CSV file (default: data/enriched_normal_ranges.csv)
--cache              Cache file path (default: data/metabolite_enrichment_cache.pkl)
--sample-size        Process only first N metabolites for testing
--dry-run            Show what would be processed without making changes
```

### `update_diet_advice_with_enriched_data.py`
```bash
--enriched-data      Path to enriched metabolite CSV file
--mode               Processing mode: add_new, overwrite_all, update_existing
--provider           LLM provider (default: openrouter_api_perplexity/sonar-pro)
--max-metabolites    Maximum number to process
--sample-size        Process only first N from enriched data
--dry-run            Show what would be processed
```

## 🎨 Enhanced Prompt Format

### Standard Prompt (Before)
```
Provide evidence-based dietary advice for managing elevated levels of DG(17:0_17:1) (HMDB ID: NOID00000).

Please include:
1. Foods to consume or increase to help reduce DG(17:0_17:1) levels
2. Foods to avoid or limit that may worsen elevated DG(17:0_17:1) levels
3. Specific dietary strategies and meal planning recommendations
```

### Enriched Prompt (After)
```
Provide specific dietary advice for managing excessive levels of the following metabolite:

Metabolite: DG(17:0_17:1) (Diglyceride) | Chemical class: Glycerolipid | Also known as: Diacylglycerol, DAG | Description: Lipid molecule involved in fat metabolism and cellular signaling.

Please provide dietary advice in JSON format for managing EXCESSIVE levels of this metabolite:

{
  "Foods to Decrease/Avoid": [
    "List specific foods, food groups, or dietary components that should be reduced or avoided"
  ],
  "Foods to Increase/Consume": [
    "List specific foods or nutrients that may help reduce levels of this metabolite"
  ],
  "Practical Dietary Strategies": [
    "List practical meal planning tips, cooking methods, or dietary patterns"
  ]
}

Focus on evidence-based dietary interventions that can help reduce DG(17:0_17:1) (Diglyceride) levels.
```

## 📊 Expected Results

### Coverage Statistics
- **Total metabolites**: 545
- **HMDB metabolites**: 252 (46%) - Full enrichment available
- **NOID metabolites**: 292 (54%) - Contextual enrichment
- **Combined metabolites**: 1 (0.2%)

### Enrichment Success Rates
- **Synonyms**: ~80% of HMDB metabolites, ~30% of NOID metabolites
- **Chemical classes**: ~85% of HMDB metabolites, ~60% of NOID metabolites  
- **Descriptions**: ~75% of HMDB metabolites, ~90% of NOID metabolites (contextual)

### Processing Time
- **Sample (10 metabolites)**: ~2 minutes
- **Full dataset (545 metabolites)**: ~30-45 minutes
- **Diet advice generation (405 metabolites)**: ~2-3 hours

## 🔄 Integration with Existing System

The enrichment system seamlessly integrates with the existing metabolite report pipeline:

1. **Maintains compatibility** with existing `normal_ranges.csv` structure
2. **Enhances existing functions** without breaking current functionality
3. **Adds new capabilities** while preserving all original features
4. **Improves report quality** through better LLM understanding

## 🎯 Benefits Summary

### For LLMs
- **Better understanding** of metabolite names and functions
- **Richer context** for generating relevant diet advice
- **Structured output** format for consistent recommendations
- **Chemical classifications** guide intervention strategies

### For Users
- **More accurate** dietary recommendations
- **Comprehensive coverage** of all metabolites
- **Better explanations** of metabolite roles
- **Actionable advice** based on scientific understanding

### For System
- **Complete metabolite database** with enhanced information
- **Scalable enrichment** process with caching
- **Robust error handling** and fallback mechanisms
- **Future-proof architecture** for additional data sources

## 🔮 Future Enhancements

1. **Additional Data Sources**
   - ChEBI ontology integration
   - KEGG pathway information
   - MetaCyc metabolic pathways

2. **Advanced Features**
   - Metabolite similarity clustering
   - Pathway-based diet advice
   - Personalized recommendations

3. **Performance Optimizations**
   - Parallel processing
   - Database caching
   - API rate optimization

---

**Ready to enhance your metabolite reports with comprehensive enrichment? Start with the demo and work your way up to full implementation!** 🚀
