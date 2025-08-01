import streamlit as st
import pandas as pd
import yaml
import re
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, XSD
from datetime import date
from copy import deepcopy

# -----------------------------------------------------------------------------
# HELPER AND CORE PROCESSING FUNCTIONS
# -----------------------------------------------------------------------------
#Limpieza y normaliza el texto para usarlo en URIs.
def clean_for_uri(text):
    if not text or pd.isna(text): return "unknown"
    a, b = 'áéíóúüñÁÉÍÓÚÜÑ', 'aeiouunAEIOUUN'
    trans = str.maketrans(a, b)
    text = str(text).translate(trans)
    text = re.sub(r'[<>:"/\\|?*(){}\[\].,;\'’]', '', text)
    text = re.sub(r'\s+', '_', text)
    text = re.sub(r'[^a-zA-Z0-9_-]', '', text)
    text = re.sub(r'_+', '_', text)
    return text.lower()

# Valida si un valor es un literal válido para RDF.
# Si es NaN o una cadena vacía, devuelve None.
def valid_literal(value):
    if pd.isna(value): return None
    s = str(value).strip()
    return s if s.lower() not in ["nan", ""] else None

# Normaliza el nombre de una organización eliminando paréntesis y abreviaturas.
# Si el nombre es vacío o NaN, devuelve None.
def normalize_organization_name(org_name):
    if not org_name or pd.isna(org_name): return None
    org_name = str(org_name).strip();
    if not org_name: return None
    org_name = re.sub(r'\s*,?\s*\([^)]*\)\s*$', '', org_name)
    org_name = re.sub(r'\s*,\s*[A-Z]{2,10}\s*$', '', org_name)
    org_name = re.sub(r'\s+', ' ', org_name).strip()
    return org_name

# Detecta el tipo de publicación basado en el título de la fuente.
# Devuelve el tipo el tipo personalizado como cadenas con prefijo.
def detect_publication_type(source_title, config):
    """
    Detecta el tipo de publicación y devuelve los nombres de tipo con prefijo como cadenas.
    No resuelve las URIs directamente para mantener la flexibilidad.
    """
    # Extrae los tipos de entidad y los tipos de publicación de la configuración.
    types = config['entity_types']
    pub_types = types.get('publication_types', {})

    # Valor por defecto si no hay título. Devuelve el tipo de artículo genérico.
    if not source_title:
        # Asume el primer tipo de la lista como el por defecto, o un fallback.
        default_type = types.get('scholarly_article', ['schema:CreativeWork'])[0]
        return default_type, None

    source_lower = source_title.lower()
    conference_patterns = ['conference', 'conf', 'congress', 'symposium', 'proceedings']
    journal_patterns = ['journal', 'revista', 'review', 'bulletin', 'transactions']
    book_series_patterns = ['lecture notes', 'series', 'advances in']

    # Devuelve el tipo de schema.org y el tipo personalizado directamente como cadenas con prefijo.
    if any(p in source_lower for p in conference_patterns):
        return "schema:Event", pub_types.get('conference')
    elif any(p in source_lower for p in journal_patterns):
        return "schema:Periodical", pub_types.get('journal')
    elif any(p in source_lower for p in book_series_patterns):
        return "schema:BookSeries", pub_types.get('book_series')
    
    # Fallback si no coincide ningún patrón.
    default_type = types.get('scholarly_article', ['schema:CreativeWork'])[0]
    return default_type, None

# Extrae el año de publicación del título de la fuente.
def extract_year_from_title(source_title):
    if not source_title: return None
    match = re.search(r'\b(20[0-2][0-9]|203[0])\b', source_title)
    return match.group(1) if match else None

# -----------------------------------------------------------------------------
# MAIN RDF GENERATION LOGIC
# -----------------------------------------------------------------------------
# Genera el grafo RDF a partir de un DataFrame y la configuración proporcionada.
def generate_rdf_graph(df, config):
    g = Graph()
    ns = {prefix: Namespace(url) for prefix, url in config['namespaces'].items()}
    for prefix, namespace_uri in ns.items(): g.bind(prefix, namespace_uri)

    def resolve_prefix(prefixed_name):
        if ':' not in prefixed_name: return URIRef(prefixed_name)
        prefix, name = prefixed_name.split(':', 1)
        return ns.get(prefix, Namespace(f"http://unknown.namespace/{prefix}/"))[name]

    BASE_URI = Namespace(config['base_uri'])
    cols = config['column_mappings']
    types = config['entity_types']
    inspection_date_str = config['settings']['inspection_date']
    inspection_date = date.today().isoformat() if inspection_date_str == 'today' else inspection_date_str
    keyword_seen, organizations_registry = {}, {}

    for _, row in df.iterrows():
        eid = clean_for_uri(str(row.get(cols['main_entity_identifier'], '')).strip())
        if eid == "unknown": continue
        article_uri = BASE_URI[eid]
        
        # MODIFIED: Handle multiple rdf:type for the main entity
        article_types = types.get('scholarly_article', [])
        for article_type in article_types:
            if article_type: g.add((article_uri, RDF.type, resolve_prefix(article_type)))
        
        g.add((article_uri, resolve_prefix('schema:identifier'), Literal(eid)))
        
        # Mapea los campos literales a propiedades RDF.
        literal_mappings = {
            'title': 'schema:name', 
            'abstract': 'schema:abstract', 
            'volume': 'schema:volumeNumber', 
            'issue': 'schema:issueNumber', 
            'page_start': 'schema:pageStart', 
            'page_end': 'schema:pageEnd'
        }
        for col_key, prop_name in literal_mappings.items():
            value = valid_literal(row.get(cols.get(col_key)))
            if value: g.add((article_uri, resolve_prefix(prop_name), Literal(value)))
        if valid_literal(row.get(cols['year'])): g.add((article_uri, resolve_prefix('schema:datePublished'), Literal(row[cols['year']], datatype=XSD.gYear)))
        if valid_literal(row.get(cols['doi'])): g.add((article_uri, resolve_prefix('schema:sameAs'), URIRef(f"https://doi.org/{row[cols['doi']]}")))
        if valid_literal(row.get(cols['link'])): g.add((article_uri, resolve_prefix('schema:url'), URIRef(row[cols['link']])))
        id_to_fullname = {}
        full_names_str = str(row.get(cols['author_full_names'], "")).strip()
        if full_names_str:
            for entry in full_names_str.split(";"):
                match = re.match(r"(.+?)\s*\((\d+)\)", entry.strip())
                if match: id_to_fullname[match.group(2).strip()] = match.group(1).strip()
        author_ids = str(row.get(cols['author_ids'], "")).split(";")
        author_abbrevs = str(row.get(cols['author_abbreviations'], "")).split(";")
        for aid, abbrev in zip(author_ids, author_abbrevs):
            aid, abbrev = aid.strip(), abbrev.strip()
            if not aid: continue
            author_uri = BASE_URI[clean_for_uri(aid)]
            g.add((author_uri, RDF.type, resolve_prefix(types['author'])))
            g.add((author_uri, resolve_prefix('schema:identifier'), Literal(aid)))
            if abbrev: g.add((author_uri, resolve_prefix('rdfs:label'), Literal(abbrev)))
            full_name = id_to_fullname.get(aid)
            if full_name:
                g.add((author_uri, resolve_prefix('schema:name'), Literal(full_name)))
                if "," in full_name:
                    parts = [p.strip() for p in full_name.split(",", 1)]
                    if len(parts) == 2:
                        g.add((author_uri, resolve_prefix('schema:familyName'), Literal(parts[0])))
                        g.add((author_uri, resolve_prefix('schema:givenName'), Literal(parts[1])))
            g.add((article_uri, resolve_prefix('schema:author'), author_uri))
        source_title = valid_literal(row.get(cols['source_title']))
        if source_title:
            periodical_id = clean_for_uri(source_title)
            periodical_uri = BASE_URI[periodical_id]
            schema_type_str, custom_type_str = detect_publication_type(source_title, config)
            if schema_type_str:
                g.add((periodical_uri, RDF.type, resolve_prefix(schema_type_str)))
            if custom_type_str:
                g.add((periodical_uri, RDF.type, resolve_prefix(custom_type_str)))
            g.add((periodical_uri, resolve_prefix('schema:name'), Literal(source_title)))
            g.add((article_uri, resolve_prefix('schema:isPartOf'), periodical_uri))
        funding_details = valid_literal(row.get(cols['funding_details']))
        if funding_details:
            for org_raw in funding_details.split(';'):
                org_normalized = normalize_organization_name(org_raw.strip())
                if not org_normalized: continue
                org_uri_id = clean_for_uri(org_normalized)
                org_uri = BASE_URI[org_uri_id]
                if org_uri_id not in organizations_registry:
                    g.add((org_uri, RDF.type, resolve_prefix(types['funding_organization'])))
                    g.add((org_uri, resolve_prefix('schema:name'), Literal(org_normalized)))
                    organizations_registry[org_uri_id] = org_normalized
                g.add((article_uri, resolve_prefix('schema:funding'), org_uri))
        
        # MODIFIED: Process keywords from the dynamic list of columns
        for column_name in config.get('keyword_settings', {}).get('columns', []):
            keywords_raw = row.get(column_name, "")
            if pd.notna(keywords_raw):
                for kw in str(keywords_raw).split(";"):
                    kw = kw.strip()
                    if not kw: continue
                    norm = clean_for_uri(kw)
                    kw_uri = BASE_URI[norm]
                    if norm not in keyword_seen:
                        g.add((kw_uri, RDF.type, resolve_prefix(types['keyword'])))
                        g.add((kw_uri, resolve_prefix('skos:prefLabel'), Literal(kw, lang='en')))
                        keyword_seen[norm] = kw
                    g.add((article_uri, resolve_prefix('dct:subject'), kw_uri))

        cited_by = valid_literal(row.get(cols['cited_by']))
        if cited_by:
            obs_id = clean_for_uri(f"{eid}-citations-{inspection_date}")
            obs_uri = BASE_URI[obs_id]
            g.add((obs_uri, RDF.type, resolve_prefix(types['citation_observation'])))
            g.add((obs_uri, resolve_prefix('schema:value'), Literal(int(cited_by), datatype=XSD.integer)))
            g.add((obs_uri, resolve_prefix('schema:observationDate'), Literal(inspection_date, datatype=XSD.date)))
            g.add((article_uri, BASE_URI["citationCount"], obs_uri))
    output_format = config['settings']['output_format']
    return g.serialize(format=output_format), len(g)

# -----------------------------------------------------------------------------
# DYNAMIC UI CONFIGURATION 
# -----------------------------------------------------------------------------
def show_interactive_config(config_data):
    """Displays a dynamic, interactive form in the sidebar to edit the configuration."""
    if 'live_config' not in st.session_state:
        st.session_state.live_config = deepcopy(config_data)
        # One-time conversion of namespaces dict to a list of dicts for the UI
        st.session_state.live_config['namespaces_ui'] = [
            {'prefix': k, 'uri': v} for k, v in st.session_state.live_config['namespaces'].items()
        ]

    live_config = st.session_state.live_config

    with st.expander("⚙️ General Settings", expanded=True):
        live_config['base_uri'] = st.text_input("Base URI", value=live_config['base_uri'])
        live_config['settings']['output_format'] = st.selectbox("Output Format", ["ttl", "xml", "n3", "nt"], index=["ttl", "xml", "n3", "nt"].index(live_config['settings']['output_format']))

    with st.expander("🔗 Namespaces"):
        st.markdown("###### Add or remove namespaces")
        # --- DYNAMIC UI for Namespaces ---
        for i, ns_item in enumerate(live_config['namespaces_ui']):
            col1, col2, col3 = st.columns([0.25, 0.65, 0.1])
            ns_item['prefix'] = col1.text_input("Prefix", value=ns_item['prefix'], key=f"ns_prefix_{i}", label_visibility="collapsed")
            ns_item['uri'] = col2.text_input("URI", value=ns_item['uri'], key=f"ns_uri_{i}", label_visibility="collapsed")
            if col3.button("🗑️", key=f"del_ns_{i}", use_container_width=True):
                live_config['namespaces_ui'].pop(i)
                st.rerun()
        if st.button("➕ Add Namespace", use_container_width=True):
            live_config['namespaces_ui'].append({'prefix': '', 'uri': ''})
            st.rerun()

    with st.expander("🏛️ Entity Types"):
        st.markdown("###### Main Article Types")
        article_types = live_config['entity_types']['scholarly_article']
        for i in range(len(article_types)):
            col1, col2 = st.columns([0.9, 0.1])
            article_types[i] = col1.text_input(f"Article Type {i+1}", value=article_types[i], label_visibility="collapsed")
            if col2.button("🗑️", key=f"del_type_{i}", use_container_width=True):
                article_types.pop(i); st.rerun()
        if st.button("➕ Add Article Type", use_container_width=True):
            article_types.append("schema:CreativeWork"); st.rerun()
        st.markdown("---");
        st.markdown("###### Other Entity Types")
        for entity, type_val in live_config['entity_types'].items():
            if entity != 'scholarly_article' and isinstance(type_val, str):
                live_config['entity_types'][entity] = st.text_input(f"Type for '{entity}'", value=type_val)

    with st.expander("🔑 Keyword Source Columns"):
        st.markdown("List all CSV columns that contain keywords.")
        keyword_cols = live_config['keyword_settings']['columns']
        for i in range(len(keyword_cols)):
            col1, col2 = st.columns([0.9, 0.1])
            keyword_cols[i] = col1.text_input(f"Keyword Column {i+1}", value=keyword_cols[i], label_visibility="collapsed")
            if col2.button("🗑️", key=f"del_kw_{i}", use_container_width=True):
                keyword_cols.pop(i); st.rerun()
        if st.button("➕ Add Keyword Column", use_container_width=True):
            keyword_cols.append("New Keyword Column"); st.rerun()

    with st.expander("🗺️ CSV Column Mappings", expanded=True):
        st.markdown("Map YAML keys to your CSV column headers.")
        for key, default_column in live_config['column_mappings'].items():
            live_config['column_mappings'][key] = st.text_input(f"`{key}` uses column:", value=default_column)

# -----------------------------------------------------------------------------
# STREAMLIT USER INTERFACE 
# -----------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="RDF Graph Generator")
st.title("📄 Papers CSV to RDF Graph Converter")
st.markdown("An interactive tool to convert structured CSV data into an RDF graph. Use the sidebar to upload and configure.")

try:
    with open("config.yaml", 'r') as f:
        default_config = yaml.safe_load(f)
except (FileNotFoundError, yaml.YAMLError) as e:
    st.error(f"FATAL: `config.yaml` not found or contains errors. Please check the file. Error: {e}")
    st.stop()

with st.sidebar:
    st.header("Controls")
    uploaded_file = st.file_uploader("1. Upload CSV File", type=["csv"])
    st.markdown("---")
    st.header("2. Configure Mapping")
    show_interactive_config(default_config)
    st.markdown("---")
    with st.expander("View Live YAML Configuration"):
        # Display the live config from session state
        st.code(yaml.dump(st.session_state.get('live_config', default_config), sort_keys=False), language='yaml')
    generate_button = st.button("🚀 Generate RDF Graph", use_container_width=True)

if generate_button:
    if uploaded_file is None:
        st.error("❌ Please upload a CSV file first.")
    else:
        try:
            # IMPORTANT: Prepare the config for the backend
            # This transforms the UI-friendly list of namespaces back into the required dictionary format
            config = deepcopy(st.session_state.live_config)
            config['namespaces'] = {
                item['prefix']: item['uri'] 
                for item in config.get('namespaces_ui', []) 
                if item.get('prefix') and item.get('uri')
            }
            del config['namespaces_ui'] # Clean up the temporary UI key

            df = pd.read_csv(uploaded_file)
            with st.spinner("Generating RDF graph based on your configuration..."):
                rdf_output, triple_count = generate_rdf_graph(df, config)

            st.success(f"✅ Graph generated successfully with {triple_count} triples!")
            st.subheader("📂 Input Data Preview")
            st.dataframe(df.head())
            output_format = config['settings']['output_format']
            st.subheader(f"✨ Generated RDF Preview (.{output_format})")
            lang = 'turtle' if output_format == 'ttl' else 'xml'
            st.code(rdf_output[:2800], language=lang)
            output_filename = f"generated_graph.{output_format}"
            st.download_button(label=f"📥 Download {output_filename}", data=rdf_output, file_name=output_filename, mime=f"text/{output_format}", use_container_width=True)
        except Exception as e:
            st.error(f"An unexpected error occurred during processing: {e}")
            st.exception(e)
else:
    st.info("Upload a file, verify your configuration in the sidebar, and click 'Generate RDF Graph' to begin.")