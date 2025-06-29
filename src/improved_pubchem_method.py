    def get_pubchem_info(self, metabolite_name: str, hmdb_id: str = "") -> Dict[str, Any]:
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
                    return result

            info = {
                'pubchem_cid': '',
                'molecular_formula': '',
                'molecular_weight': '',
                'canonical_smiles': '',
                'inchi': '',
                'pubchem_synonyms': [],
                'compound_description': '',
                'biological_summary': '',
                'pharmacology': '',
                'literature_abstracts': [],
                'source': 'PubChem',
                'timestamp': datetime.now().isoformat(),
                'success': True
            }

            if 'PC_Compounds' in data and data['PC_Compounds']:
                compound = data['PC_Compounds'][0]

                # Extract CID
                cid = ''
                if 'id' in compound and 'id' in compound['id'] and 'cid' in compound['id']['id']:
                    cid = str(compound['id']['id']['cid'])
                    info['pubchem_cid'] = cid

                # Extract properties
                if 'props' in compound:
                    for prop in compound['props']:
                        if 'urn' in prop and 'label' in prop['urn']:
                            label = prop['urn']['label']
                            if label == 'Molecular Formula' and 'value' in prop:
                                info['molecular_formula'] = prop['value']['sval']
                            elif label == 'Molecular Weight' and 'value' in prop:
                                if 'fval' in prop['value']:
                                    info['molecular_weight'] = str(prop['value']['fval'])
                                elif 'sval' in prop['value']:
                                    info['molecular_weight'] = str(prop['value']['sval'])
                            elif label == 'SMILES' and 'value' in prop:
                                info['canonical_smiles'] = prop['value']['sval']
                            elif label == 'InChI' and 'value' in prop:
                                info['inchi'] = prop['value']['sval']
                
                # If we have a CID, fetch additional information using PUG-View
                if cid:
                    self._fetch_pubchem_additional_data(cid, info)

            # Calculate time taken
            end_time = time.time()
            elapsed_time = end_time - start_time
            
            # Add timing information
            info['timing'] = {
                'source': 'pubchem',
                'elapsed_seconds': round(elapsed_time, 2),
                'from_cache': False
            }
            
            logger.debug(f"PubChem fetch took {elapsed_time:.2f} seconds for {metabolite_name}")
            
            # Cache the result
            self.cache[cache_key] = info

            # Rate limiting
            time.sleep(RATE_LIMIT_DELAY)
            
            return info
            
        except Exception as e:
            logger.error(f"Error in get_pubchem_info for {metabolite_name}: {e}")
            # Return empty result with error info
            result = {
                'pubchem_cid': '',
                'molecular_formula': '',
                'molecular_weight': '',
                'success': False,
                'source': 'PubChem',
                'error': str(e)
            }
            self.cache[cache_key] = result
            return result
