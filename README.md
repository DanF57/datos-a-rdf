# 📄 Papers CSV to RDF Graph Converter

[![Streamlit App](https://img.shields.io/badge/Built%20with-Streamlit-orange)](https://streamlit.io/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![RDFLib](https://img.shields.io/badge/RDFLib-used-blueviolet)](https://rdflib.dev/)

Convierte archivos CSV con metadatos de artículos científicos en grafos RDF exportables.  
Una herramienta interactiva construida con **Streamlit**, **RDFlib** y configurada mediante YAML.

---

## 🚀 Características

- 📁 Carga archivos CSV y previsualiza sus datos
- ⚙️ Edición en vivo de configuración RDF desde la barra lateral
- 🏷️ Mapeo flexible de columnas CSV a propiedades semánticas
- 🧠 Detección automática del tipo de publicación (journal, conferencia, etc.)
- 📤 Exportación del grafo RDF en formatos `.ttl`, `.xml`, `.n3`, `.nt`
- 🔍 Visualización del RDF y descarga del archivo generado

## 🛠️ Instalación

```bash
# Clona el repositorio
git clone [https://github.com/DanF57/datos-a-rdf](https://github.com/DanF57/datos-a-rdf)
cd datos-a-rdf

# Instala las dependencias
pip install -r requirements.txt

# Ejecuta la aplicación
streamlit run app.py
````

---

## 📁 Estructura del proyecto

```
datos-a-rdf/
├── app.py             # Código principal de la app Streamlit
├── config.yaml        # Archivo de configuración editable
├── requirements.txt   # Dependencias del proyecto
└── README.md
```

---

## ⚙️ Configuración (`config.yaml`)

Define namespaces RDF, tipos de entidades y mapeos entre columnas del CSV y propiedades RDF.

```yaml
namespaces:
  schema: "https://schema.org/"
  skos: "http://www.w3.org/2004/02/skos/core#"

entity_types:
  scholarly_article:
    - "schema:ScholarlyArticle"
  author: "schema:Person"
  keyword: "skos:Concept"

column_mappings:
  title: "Title"
  doi: "DOI"
  author_ids: "Author(s) ID"
```

Puedes editar esta configuración dinámicamente desde la interfaz o directamente en el archivo.

---

## ✨ Ejemplo de salida

Dado un CSV con esta fila:

| EID | Title              | DOI        | Author(s) ID |
| --- | ------------------ | ---------- | ------------ |
| 123 | "AI in Healthcare" | 10.1234/ai | a1;a2        |

Generará triples RDF como:

```turtle
<http://deflores.org/utpl/vocab/123>
    a schema:ScholarlyArticle ;
    schema:identifier "123" ;
    schema:name "AI in Healthcare" ;
    schema:author <http://deflores.org/utpl/vocab/a1>, <http://deflores.org/utpl/vocab/a2> .
```

---

## 🧪 Casos de uso

* Repositorios académicos institucionales
* Exportación de datos hacia triplestores
* Transformación de datos bibliográficos en ontologías ligeras
* Cumplimiento con principios FAIR

---

## ✅ Requisitos

* Python 3.9+
* Archivo CSV estructurado (UTF-8)

---

## 🙋‍♂️ Autor
**Daniel Flores**
✉️ *deflores13@utpl.edu.ec*
