# 🏥 AyuReg - Indian Clinical Registry & Medical Intelligence Portal

AyuReg is a modern clinical assistant and medicine intelligence web portal designed to search, catalog, and query national medicine datasets. It indexes a large **50,000+ medicine registry** using a hybrid structured query + vector search RAG pipeline.

Inspired by clinical and epidemiologic portals such as the **Indian Council of Medical Research (ICMR)** Data Portal.

---

## 🚀 Key Features

1.  **📊 Analytics Dashboard**: Live visual statistics showing total registry count, classification split (Prescription Rx vs Over-the-Counter OTC), and SVG-rendered distributions of medicine categories and manufacturers.
2.  **🔎 Medicine Directory (SQLite-Powered)**: A lightning-fast paginated directory to search and filter 50,000+ records instantly by Name, Category, or Classification. Includes expander panels displaying indications, dosage guidelines, side effects, and stock alternatives.
3.  **💬 Clinical Chatbot (Guidelines RAG)**: A multi-turn conversational AI assistant that queries national guidelines from a vector database (ChromaDB + HuggingFace) and dynamically merges them with live SQLite records to recommend in-stock alternatives and treatment protocols.

---

## 🛠️ Architecture Stack

*   **Frontend**: React (Vite SPA) styled with a clean clinical light/white theme using CSS variables and micro-animations.
*   **Backend**: Python FastAPI providing endpoints for paginated search, analytical stats, database rebuilds, and streaming LLM tokens.
*   **Structured Store**: SQLite (`medicines.db`) for indexing and querying the 50,000+ medicine dataset.
*   **Unstructured Store**: ChromaDB for semantic vector retrieval of clinical guidelines.
*   **Embeddings**: HuggingFace `all-MiniLM-L6-v2` (sentence-transformers) running locally.
*   **Large Language Model**: Mistral 7B via Ollama (`mistral`).

---

## 📦 Installation & Setup

### 1. Prerequisites
*   [Node.js](https://nodejs.org/) (v18+)
*   Python (3.10+)
*   [Ollama](https://ollama.com/) running locally:
    ```bash
    ollama serve
    ollama pull mistral
    ```

### 2. Quick Launch
Simply run the launcher script:
*   Double-click `run_app.bat` from your file explorer.
    *   *This will concurrently start the FastAPI backend on port `8000` and the React frontend Vite dev server on port `5173`.*

### 3. Manual Startup

#### Backend
Activate the virtual environment and launch FastAPI using Uvicorn:
```bash
call venv\Scripts\activate
uvicorn backend.main:app --reload --port 8000
```

#### Frontend
Navigate to the `frontend/` directory, install packages, and start Vite:
```bash
cd frontend
npm install
npm run dev
```

---

## 🧪 Database & Vector Store Rebuilding
If the dataset changes or you need to initialize the databases from scratch, you can click **"🔄 Rebuild Registry"** in the top-right of the web portal, or trigger the endpoint manually:
```bash
curl -X POST http://localhost:8000/api/rebuild
```
*This will parse the `medicine_dataset.csv` file, build the SQLite indices, and embed the clinical guidelines in ChromaDB.*
