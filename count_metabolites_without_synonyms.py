import json

def main():
    with open("output_dir_all_by_PubChemID/metabolite_enriched_data.json", "r") as f:
        data = json.load(f)

    total = 0
    no_synonyms = 0
    for name, entry in data.items():
        total += 1
        synonyms = entry.get("all_synonyms", [])
        # Consider no synonyms if the list is empty or contains only empty/whitespace strings
        if not synonyms or all((not s or str(s).strip() == "") for s in synonyms):
            no_synonyms += 1

    print(f"Total metabolites: {total}")
    print(f"Metabolites without synonyms: {no_synonyms}")
    if total > 0:
        print(f"Percentage without synonyms: {no_synonyms/total*100:.2f}%")

if __name__ == "__main__":
    main()
