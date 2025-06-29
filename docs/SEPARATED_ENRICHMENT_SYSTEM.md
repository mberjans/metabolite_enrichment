# 🔄 Separated Metabolite Enrichment System

## Overview

The metabolite enrichment system has been **separated into two distinct, modular components** for better maintainability, flexibility, and separation of concerns:

1. **🧬 Metabolite Data Enricher** - Obtains synonyms, classes, and descriptions
2. **🍎 Enhanced Diet Advice Generator** - Uses enriched data to generate diet advice

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    SEPARATED ARCHITECTURE                       │
└─────────────────────────────────────────────────────────────────┘

📊 INPUT DATA
├── input/normal_ranges.csv (545 metabolites)
└── .env (API keys)

🧬 PHASE 1: METABOLITE ENRICHMENT
├── metabolite_data_enricher.py
├── ├── HMDB web scraping
├── ├── PubChem API calls  
├── ├── Contextual pattern matching
├── └── Caching system
├── 
├── OUTPUT:
├── ├── data/metabolite_enriched_data.json (structured data)
├── ├── data/enriched_normal_ranges.csv (compatibility)
└── └── data/metabolite_enrichment_cache.pkl (cache)

🍎 PHASE 2: DIET ADVICE GENERATION  
├── enhanced_diet_advice_generator.py
├── ├── Load enriched data from JSON
├── ├── Create enhanced LLM prompts
├── ├── Call OpenRouter/Perplexity APIs
├── └── Save structured diet advice
├── 
├── OUTPUT:
├── ├── input/metabolite_info_high.json (updated)
└── └── input/metabolite_info_low.json (updated)

📋 INTEGRATION
└── Existing report generation uses enhanced advice
```

## 🎯 Benefits of Separation

### **1. Modularity**
- **Independent execution** - Run enrichment and diet advice generation separately
- **Flexible scheduling** - Enrich data once, generate advice multiple times
- **Easier maintenance** - Modify one component without affecting the other

### **2. Data Persistence**
- **Reusable enriched data** - Store enriched information in JSON for multiple uses
- **Incremental updates** - Add new metabolites without re-enriching existing ones
- **Version control** - Track changes to enriched data over time

### **3. Performance Optimization**
- **Faster diet advice generation** - No need to re-fetch HMDB/PubChem data
- **Reduced API calls** - Enrichment happens once, diet advice uses cached data
- **Parallel processing** - Can run multiple diet advice generators simultaneously

### **4. Better Error Handling**
- **Isolated failures** - Enrichment errors don't affect diet advice generation
- **Retry mechanisms** - Re-run failed components independently
- **Debugging** - Easier to identify and fix issues in specific components

## 📁 File Structure

```
src/
├── metabolite_data_enricher.py          # Phase 1: Data enrichment
├── enhanced_diet_advice_generator.py    # Phase 2: Diet advice generation
├── demo_metabolite_enrichment.py        # Original demo (still works)
└── retrieve_missing_diet_advice.py      # Enhanced with new functions

data/
├── metabolite_enriched_data.json        # Main enriched data store
├── enriched_normal_ranges.csv           # CSV compatibility format
└── metabolite_enrichment_cache.pkl      # API call cache

input/
├── normal_ranges.csv                    # Original metabolite data
├── metabolite_info_high.json            # Enhanced diet advice (high)
└── metabolite_info_low.json             # Enhanced diet advice (low)
```

## 🚀 Usage Instructions

### **Phase 1: Metabolite Data Enrichment**

#### **Test with Sample Data**
```bash
# Show what would be enriched
python src/metabolite_data_enricher.py --sample-size 10 --dry-run

# Enrich 10 metabolites for testing
python src/metabolite_data_enricher.py --sample-size 10
```

#### **Full Enrichment (30-45 minutes)**
```bash
# Enrich all 545 metabolites
python src/metabolite_data_enricher.py

# Check existing enriched data
python src/metabolite_data_enricher.py --load-existing
```

#### **Output Files**
- `data/metabolite_enriched_data.json` - **Main enriched data store**
- `data/enriched_normal_ranges.csv` - CSV format for compatibility
- `data/metabolite_enrichment_cache.pkl` - Cache for API calls

### **Phase 2: Enhanced Diet Advice Generation**

#### **Check Statistics**
```bash
# Show enrichment coverage and missing advice
python src/enhanced_diet_advice_generator.py --stats
```

#### **Test with Sample Data**
```bash
# Show what would be processed
python src/enhanced_diet_advice_generator.py --max-metabolites 5 --dry-run

# Generate advice for 5 metabolites
python src/enhanced_diet_advice_generator.py --max-metabolites 5
```

#### **Full Diet Advice Generation (2-3 hours)**
```bash
# Generate advice for all missing metabolites
python src/enhanced_diet_advice_generator.py --mode add_new

# Process specific metabolites
python src/enhanced_diet_advice_generator.py --hmdb-ids "HMDB0000687,HMDB0000123"
```

## 📊 Data Formats

### **Enriched Data JSON Structure**
```json
{
  "HMDB0000687": {
    "hmdb_id": "HMDB0000687",
    "original_name": "L-Leucine",
    "enhanced_name": "L-Leucine (Branched-Chain Amino Acid)",
    "all_synonyms": ["L-Leucine", "2-Amino-4-methylpentanoic acid", "BCAA"],
    "chemical_classes": ["Amino acids", "Branched-chain amino acids"],
    "taxonomy": {
      "kingdom": "Organic compounds",
      "super_class": "Organic acids and derivatives",
      "class": "Carboxylic acids and derivatives",
      "sub_class": "Amino acids, peptides, and analogues",
      "direct_parent": "Alpha amino acids"
    },
    "chemical_properties": {
      "iupac_name": "(2S)-2-amino-4-methylpentanoic acid",
      "common_name": "Leucine",
      "molecular_formula": "C6H13NO2",
      "molecular_weight": "131.17",
      "canonical_smiles": "CC(C)CC(C(=O)O)N"
    },
    "descriptions": {
      "hmdb_description": "Essential amino acid crucial for protein synthesis...",
      "contextual_description": "Building block of proteins...",
      "llm_description": "Metabolite: L-Leucine | Chemical class: Amino acid..."
    },
    "database_ids": {
      "hmdb_id": "HMDB0000687",
      "pubchem_cid": "6106"
    },
    "data_sources": {
      "hmdb_success": true,
      "pubchem_success": true,
      "has_contextual_info": true
    },
    "original_data": {
      "low_level": "80.0",
      "high_level": "200.0",
      "sd": "30.0",
      "reference": "PMID: 12345678"
    },
    "enrichment_metadata": {
      "enriched_timestamp": "2025-05-22T14:30:00.000000",
      "enricher_version": "1.0.0"
    }
  }
}
```

### **Enhanced Diet Advice Structure**
```json
{
  "HMDB0000687": {
    "metabolite": "L-Leucine (Branched-Chain Amino Acid)",
    "abnormality": "high",
    "advice": "{\n  \"Foods to Decrease/Avoid\": [...],\n  \"Foods to Increase/Consume\": [...],\n  \"Practical Dietary Strategies\": [...]\n}",
    "source": "openrouter_api_perplexity/sonar-pro",
    "enhanced_prompt": true,
    "enriched_data_available": true,
    "query": "Enhanced prompt with synonyms and classes...",
    "enrichment_metadata": {
      "enhanced_name": "L-Leucine (Branched-Chain Amino Acid)",
      "synonyms_count": 3,
      "chemical_classes_count": 2,
      "has_hmdb_data": true,
      "has_pubchem_data": true,
      "has_contextual_info": true
    }
  }
}
```

## 🔧 Command Line Options

### **metabolite_data_enricher.py**
```bash
--input              Input CSV file (default: input/normal_ranges.csv)
--json-output        Output JSON file (default: data/metabolite_enriched_data.json)
--csv-output         Output CSV file (default: data/enriched_normal_ranges.csv)
--cache              Cache file path (default: data/metabolite_enrichment_cache.pkl)
--sample-size        Process only first N metabolites for testing
--dry-run            Show what would be processed without making changes
--load-existing      Load existing enriched data and show statistics
```

### **enhanced_diet_advice_generator.py**
```bash
--enriched-data      Path to enriched metabolite JSON file
--mode               Processing mode: add_new, overwrite_all, update_existing
--provider           LLM provider/model (default: perplexity/sonar-pro)
--max-metabolites    Maximum number to process (for testing)
--hmdb-ids           Comma-separated list of specific HMDB IDs to process
--dry-run            Show what would be processed without making changes
--stats              Show statistics about enriched data and missing advice
```

## 🔄 Integration with Existing System

### **Backward Compatibility**
- **Existing functions** continue to work unchanged
- **Original files** remain in place and functional
- **Report generation** automatically uses enhanced advice when available

### **Enhanced Functions Available**
```python
# Load enriched data
from metabolite_data_enricher import load_enriched_metabolite_data
enriched_data = load_enriched_metabolite_data()

# Get specific metabolite info
from metabolite_data_enricher import get_metabolite_enriched_info
metabolite_info = get_metabolite_enriched_info("HMDB0000687")

# Create enhanced prompts
from metabolite_data_enricher import create_enhanced_prompt_from_enriched_data
prompt = create_enhanced_prompt_from_enriched_data("HMDB0000687", "high")
```

## 📈 Expected Performance

### **Phase 1: Enrichment**
- **Sample (10 metabolites)**: ~2 minutes
- **Full dataset (545 metabolites)**: ~30-45 minutes
- **Cache hits**: Instant (subsequent runs)

### **Phase 2: Diet Advice**
- **Sample (5 metabolites)**: ~2 minutes
- **Missing metabolites (405)**: ~2-3 hours
- **Enhanced vs basic**: Same API time, better quality

### **Storage Requirements**
- **Enriched JSON**: ~2-5 MB (structured data)
- **Cache file**: ~10-20 MB (API responses)
- **CSV compatibility**: ~1-2 MB (flattened data)

## 🎯 Recommended Workflow

### **Initial Setup**
1. **Enrich metabolite data** (one-time, 30-45 minutes)
2. **Generate missing diet advice** (one-time, 2-3 hours)
3. **Use enhanced system** for all future operations

### **Ongoing Usage**
1. **Add new metabolites** to normal_ranges.csv
2. **Re-run enrichment** for new metabolites only
3. **Generate diet advice** for new metabolites
4. **System automatically** uses enhanced data

### **Maintenance**
1. **Update enriched data** periodically (monthly/quarterly)
2. **Refresh diet advice** when needed (new research, model updates)
3. **Monitor cache size** and clean up if needed

---

**The separated system provides maximum flexibility while maintaining all the benefits of the integrated approach!** 🚀🔬
