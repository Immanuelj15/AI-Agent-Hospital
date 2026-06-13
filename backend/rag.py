# backend/rag.py
import os
import shutil
import pandas as pd
try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from langchain_text_splitters import CharacterTextSplitter
from backend.db import get_db_connection

CHROMA_PATH = os.path.join("backend", "chroma_store")
MODEL_NAME = "phi3:latest"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# ICMR-style Mock Clinical Treatment Guidelines
CLINICAL_GUIDELINES = [
    {
        "title": "Antibiotic Stewardship and Bacterial Infection Guidelines",
        "content": "ICMR Guidelines for Antibiotic Use: Antibiotics (e.g., Amoxicillin, Ibupromycin, Dextrophen) are strictly indicated for bacterial infections. Use in viral infections is inappropriate and contributes to antimicrobial resistance. Dosage forms include Tablets, Capsules, and Injections. Side effects commonly involve GI distress (diarrhea, cramping, nausea). For out-of-stock antibiotics, pharmacists must recommend equivalent class alternatives from available stock."
    },
    {
        "title": "Antiviral Therapy for Viral Outbreaks",
        "content": "ICMR Guidelines for Antiviral Stewardship: Antiviral medications (e.g., Ibuprocillin, Metovir, Acetomycin) are deployed for active viral replica control. Treatment should begin within 48 hours of symptom onset. Regular monitoring of liver and renal function is advised for prolonged treatments. Side effects include headache, fatigue, and muscle pain. Keep patient hydrated."
    },
    {
        "title": "Management of Type 2 Diabetes",
        "content": "Clinical Registry Guidelines for Antidiabetic Agents: For Type 2 Diabetes management, antidiabetic drugs (e.g., Acetocillin, Dextrocillin, Claricillin) are first-line therapies alongside lifestyle modifications. Regular monitoring of HbA1c and daily blood glucose tracking is critical. Common side effects include hypoglycemia, abdominal discomfort, and metallic taste. Alternatives should be recommended if patient experiences severe GI intolerance."
    },
    {
        "title": "Fungal Infection Treatment Protocols",
        "content": "Guidelines for Antifungal Care: Fungal infections (e.g., Clarinazole, Acetonazole, Cefmet) are treated with topical creams, ointments, or systemic tablets/syrups. Course completion is vital to prevent recurrence. Side effects include localized skin irritation, itching, or redness. Oral antifungals require hepatic enzyme tracking in chronic usage."
    },
    {
        "title": "Fever Management & Antipyretic Safety",
        "content": "Fever and Antipyretic Usage Guidelines: Antipyretics (e.g., Cefcillin, Metovir, Cefstatin) are indicated for symptomatic reduction of elevated body temperature. Daily limits must not be exceeded to prevent hepatotoxicity. Ensure adequate hydration and look for alternative indications (e.g., infection) if fever persists beyond 3 days."
    },
    {
        "title": "Analgesic Pain Management",
        "content": "Pain and Inflammation Management: Analgesics (e.g., Acetomycin, Ibupronazole, Metocillin) are used for acute or chronic pain relief. Over-the-counter NSAIDs carry risk of gastric ulcers and cardiovascular events with long-term high-dose use. Common side effects include stomach pain, heartburn, and dizziness. Alternatives must be checked for allergy compatibility."
    },
    {
        "title": "Depression and Mood Disorder Treatments",
        "content": "Depressive Disorder Guidelines: Antidepressant classes (e.g., Ibuprovir, Cefmet, Clariprofen) require strict compliance and continuous psychiatric follow-up. Therapeutic effects may take 2-4 weeks to manifest. Side effects include drowsiness, dry mouth, sleep cycle shifts, and weight changes. Discontinuation must be tapered under clinical supervision."
    },
    {
        "title": "Wound Care and Antiseptic Protocols",
        "content": "Wound Management and Antiseptics: Localized wounds are cleaned with antiseptics (e.g., Metoprofen, Metophen, Ibuprostatin) in cream, ointment, or tablet forms to prevent secondary bacterial infection. Check classification (Prescription vs OTC) before dispensing. Side effects are minor, mostly localized dryness or hypersensitivity."
    }
]

def build_vectorstore(persist_dir=CHROMA_PATH):
    """Builds the ChromaDB vector store containing medical research guidelines."""
    print("Loading Clinical Guidelines...")
    docs = []
    for g in CLINICAL_GUIDELINES:
        content = f"Title: {g['title']}\nContent: {g['content']}\n"
        metadata = {"title": g['title']}
        docs.append(Document(page_content=content, metadata=metadata))
        
    # Clean up existing vector database directory
    if os.path.exists(persist_dir):
        print(f"Clearing existing vector store at {persist_dir}...")
        try:
            shutil.rmtree(persist_dir)
        except Exception as e:
            print(f"Warning: Could not fully delete directory: {e}")
            
    print(f"Creating Vector Store using {EMBEDDING_MODEL} embeddings...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    
    vectordb = Chroma.from_documents(
        documents=docs, 
        embedding=embeddings, 
        persist_directory=persist_dir
    )
    print("Guidelines Vector Store successfully built.")
    return vectordb

def add_document_to_vectorstore(text, title, persist_dir=CHROMA_PATH):
    """Splits text and adds the documents to the guidelines vector store."""
    if not text.strip():
        return False
        
    print(f"Adding clinical guideline: '{title}' to vector store...")
    text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    docs = [Document(page_content=f"Title: {title}\nContent: {text}\n", metadata={"title": title})]
    split_docs = text_splitter.split_documents(docs)
    
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vectordb = Chroma(persist_directory=persist_dir, embedding_function=embeddings)
    vectordb.add_documents(split_docs)
    print("Guidelines vector store successfully updated.")
    return True

def extract_entities_and_query_db(standalone_query):
    """
    Queries the SQLite database using FTS5 for any matching medicines, categories, 
    or indications in the query to provide real-time stock details for RAG.
    """
    # Clean the query for FTS5 matching
    clean_search = "".join([c if c.isalnum() or c.isspace() else " " for c in standalone_query]).strip()
    
    # Exclude common stopwords to prevent irrelevant high-frequency matching
    stopwords = {"what", "is", "its", "the", "are", "you", "have", "for", "and", "can", "with", "this", "that", "from", "please", "show", "tell", "price", "stock", "dosage", "form", "manufacturer"}
    words = [w for w in clean_search.lower().split() if w not in stopwords and len(w) > 2]
    search_terms = " OR ".join([f"{w}*" for w in words])
    
    if not search_terms:
        return ""
        
    db_context = ""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Search FTS5 for up to 5 matching medicines
        sql = """
        SELECT m.* FROM medicines m 
        JOIN medicines_fts f ON m.id = f.rowid 
        WHERE medicines_fts MATCH ? 
        LIMIT 5
        """
        cursor.execute(sql, (search_terms,))
        rows = cursor.fetchall()
        
        if rows:
            db_context += "\n--- Real-time Medicine Stock Registry Matches ---\n"
            for r in rows:
                db_context += (
                    f"Medicine: {r['name']} ({r['strength']})\n"
                    f"- Category: {r['category']} | Indication: {r['indication']}\n"
                    f"- Stock Status: {r['stock']} | Price: ${r['price']:.2f} | Manufacturer: {r['manufacturer']}\n"
                    f"- Classification: {r['classification']}\n"
                    f"- Dosage: {r['dosage_instruction']}\n"
                    f"- Side Effects: {r['side_effects']}\n"
                )
                if r['stock'] == 'No':
                    # Find alternative in same category that is in stock
                    cursor.execute(
                        "SELECT name, price FROM medicines WHERE category = ? AND stock = 'Yes' LIMIT 1",
                        (r['category'],)
                    )
                    alt = cursor.fetchone()
                    alt_name = alt['name'] if alt else "Generic Substitute"
                    db_context += f"- Recommended Available Alternative: {alt_name}\n"
                db_context += "\n"
    except Exception as e:
        print(f"Database query error during RAG: {e}")
    finally:
        conn.close()
        
    return db_context

def stream_rag_response(question, chat_history, role="clerk"):
    """Generates a streamed clinical RAG response combining guidelines and SQL data."""
    llm = ChatOllama(
        model=MODEL_NAME, 
        temperature=0.1, 
        base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434")
    )
    
    # 1. Contextualize user question if history exists
    standalone_question = question
    if chat_history:
        contextualize_q_system_prompt = (
            "You are an assistant that reformulates user questions.\n"
            "Given a chat history and the latest user question which might reference pronouns or context in the chat history, "
            "formulate a standalone question that can be understood without the chat history.\n"
            "CRITICAL RULES:\n"
            "1. Do NOT answer the question.\n"
            "2. Do NOT add any introductory, conversational, or explanatory text (e.g., do NOT say 'Here is the standalone question:', 'Sure, here it is', etc.).\n"
            "3. Output ONLY the reformulated question and nothing else."
        )
        contextualize_q_prompt = ChatPromptTemplate.from_messages([
            ("system", contextualize_q_system_prompt),
            # Few-shot examples
            ("human", "Do you have Acetocillin?"),
            ("ai", "No, Acetocillin is out of stock. We suggest Metformin as an alternative."),
            ("human", "What is its price?"),
            ("ai", "What is the price of Metformin?"),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{question}"),
        ])
        contextualizer = contextualize_q_prompt | llm | StrOutputParser()
        standalone_question = contextualizer.invoke({"question": question, "chat_history": chat_history})
        standalone_question = standalone_question.strip().strip('"').strip("'")
        print(f"Contextualized Query: {standalone_question}")
        
    # 2. Retrieve Guidelines from ChromaDB
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vectordb = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
    retriever = vectordb.as_retriever(search_kwargs={"k": 2})
    guideline_docs = retriever.invoke(standalone_question)
    guideline_context = "\n".join(doc.page_content for doc in guideline_docs)
    
    # 3. Retrieve Live Database Matches
    db_context = extract_entities_and_query_db(standalone_question)
    
    # Merge context
    combined_context = f"=== CLINICAL RESEARCH GUIDELINES ===\n{guideline_context}\n{db_context}"
    
    # 4. Configure system instructions based on the active role
    role_instruction = f"The user is logged in as a: {role.upper()}."
    if role == "clerk":
        role_instruction += " Restrict giving authorization details. Emphasize that Prescription-only (Rx) medications cannot be dispensed without doctor signature."
    else:
        role_instruction += " Full clinician access. You can guide them through prescribing and authorization steps."

    # Generate Answer via RAG Chain
    system_prompt = f"""You are a senior clinical AI assistant for AyuReg Medical shop.
    {role_instruction}
    
    Use the following pieces of context (composed of medical guidelines and real-time database stock records) to answer the user's question.
    
    CRITICAL MEDICAL SAFETY RULES:
    1. Under no circumstances should you make up or hallucinate any medicine names, stock status, prices, indications, dosages, or side effects.
    2. If the user asks about a medicine, you must only answer based on the provided "Real-time Medicine Stock Registry Matches" or "Medicine Details" context.
    3. If the query cannot be answered using the provided context, you MUST state exactly: "I do not have clinical registry records for that query."
    4. If the user asks general or off-topic questions that are not related to medical treatments, drugs, or clinical registry search, politely decline to answer.

    RULES:
    1. If the user asks for a medicine, look up its stock status in the provided stock registry or medicine details.
    2. If out of stock, explicitly say it is OUT OF STOCK and recommend the listed 'Recommended Available Alternative' or suggest a medicine from the same Category that is in stock.
    3. Include dosage instructions and side effects when relevant or requested.
    4. Speak professionally, concisely, and cite the guidelines or stock records when answering.
    5. If details are not in the context and cannot be found in the database, state: "I do not have clinical registry records for that query."

    Context:
    {{context}}"""
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}"),
    ])
    
    chain = prompt | llm | StrOutputParser()
    
    return chain.stream({
        "context": combined_context,
        "chat_history": chat_history,
        "question": standalone_question
    })
