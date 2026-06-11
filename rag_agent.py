# rag_agent.py
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

# Configuration
DATA_PATH = os.path.join("data", "medicines.csv")
CHROMA_PATH = "chroma_store"
MODEL_NAME = "mistral"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

def load_medicine_data(csv_path):
    """Loads medicine data from CSV and converts to Document objects."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Data file not found at {csv_path}")

    df = pd.read_csv(csv_path)
    docs = []
    for _, row in df.iterrows():
        content = (
            f"Medicine ID: {row['Medicine_ID']}\n"
            f"Medicine Name: {row['Medicine_Name']}\n"
            f"Strength: {row['Strength']}\n"
            f"Use Case: {row['Use_Case']}\n"
            f"Alternative: {row['Alternative']}\n"
            f"Stock Status: {row['Stock']}\n"
            f"Dosage Instruction: {row['Dosage_Instruction']}\n"
            f"Side Effects: {row['Side_Effects']}\n"
            f"Price: ${row['Price']}\n"
            f"Manufacturer: {row['Manufacturer']}\n"
        )
        metadata = {
            "name": str(row['Medicine_Name']).lower(),
            "stock": str(row['Stock']),
            "use_case": str(row['Use_Case']).lower()
        }
        docs.append(Document(page_content=content, metadata=metadata))
    return docs

def build_vectorstore(csv_path=DATA_PATH, persist_dir=CHROMA_PATH):
    """Builds or updates the ChromaDB vector store after clearing the directory."""
    print("Loading data...")
    docs = load_medicine_data(csv_path)
    
    # Clean up existing vector database directory to prevent duplicates
    if os.path.exists(persist_dir):
        print(f"Clearing existing vector store at {persist_dir}...")
        try:
            shutil.rmtree(persist_dir)
        except Exception as e:
            print(f"Warning: Could not fully delete directory: {e}")
            
    print("Splitting text...")
    text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
    split_docs = text_splitter.split_documents(docs)

    print(f"Creating Vector Store using {EMBEDDING_MODEL} embeddings...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    
    vectordb = Chroma.from_documents(
        documents=split_docs, 
        embedding=embeddings, 
        persist_directory=persist_dir
    )
    print("Vector Store created successfully.")
    return vectordb

def get_hybrid_context(standalone_question, df, retriever):
    """Retrieves relevant medicine documents using a hybrid direct name/alternative matching + vector search approach."""
    matched_docs = []
    clean_q = standalone_question.lower()
    
    # 1. Direct Name & Alternative Match
    for _, row in df.iterrows():
        med_name = str(row['Medicine_Name']).lower()
        alt_name = str(row['Alternative']).lower()
        
        # Match if the query contains either the primary name or the alternative name
        if med_name in clean_q or alt_name in clean_q:
            content = (
                f"Medicine ID: {row['Medicine_ID']}\n"
                f"Medicine Name: {row['Medicine_Name']}\n"
                f"Strength: {row['Strength']}\n"
                f"Use Case: {row['Use_Case']}\n"
                f"Alternative: {row['Alternative']}\n"
                f"Stock Status: {row['Stock']}\n"
                f"Dosage Instruction: {row['Dosage_Instruction']}\n"
                f"Side Effects: {row['Side_Effects']}\n"
                f"Price: ${row['Price']}\n"
                f"Manufacturer: {row['Manufacturer']}\n"
            )
            metadata = {
                "name": med_name,
                "stock": str(row['Stock']),
                "use_case": str(row['Use_Case']).lower()
            }
            # Avoid duplicate direct matches
            if not any(doc.metadata["name"] == med_name for doc in matched_docs):
                matched_docs.append(Document(page_content=content, metadata=metadata))
            
    # 2. Semantic Search Match: Fetch k=3 documents from VectorDB
    vector_docs = retriever.invoke(standalone_question)
    
    # Combine results, avoiding duplicate page content
    seen_content = {doc.page_content for doc in matched_docs}
    for doc in vector_docs:
        if doc.page_content not in seen_content:
            matched_docs.append(doc)
            
    return "\n\n".join(doc.page_content for doc in matched_docs)

def stream_rag_response(question, chat_history):
    """Generates a streamed response using conversational memory and hybrid retrieval."""
    llm = ChatOllama(model=MODEL_NAME, temperature=0.1)
    
    # 1. Contextualize user question if there is history
    standalone_question = question
    if chat_history:
        # Strict contextualization prompt with few-shot examples to force clean output from Mistral
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
            # Few-shot Example 1
            ("human", "Do you have Ibuprofen?"),
            ("ai", "No, Ibuprofen is out of stock. We suggest Diclofenac as an alternative."),
            ("human", "What is its price?"),
            ("ai", "What is the price of Diclofenac?"),
            # Few-shot Example 2
            ("human", "I need something for a throat infection."),
            ("ai", "We have Azithromycin available for throat infections."),
            ("human", "How should I take it?"),
            ("ai", "What are the dosage instructions for Azithromycin?"),
            # Real history
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{question}"),
        ])
        contextualizer = contextualize_q_prompt | llm | StrOutputParser()
        standalone_question = contextualizer.invoke({"question": question, "chat_history": chat_history})
        # Strip any surrounding quotes or spacing the LLM might have output
        standalone_question = standalone_question.strip().strip('"').strip("'")
        print(f"Contextualized Question: {standalone_question}")
    
    # 2. Setup VectorDB Retriever
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vectordb = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
    retriever = vectordb.as_retriever(search_kwargs={"k": 3})
    
    # Load raw CSV for direct keyword lookup
    df = pd.read_csv(DATA_PATH)
    
    # 3. Retrieve Context via Hybrid Approach
    context = get_hybrid_context(standalone_question, df, retriever)
    
    # 4. Generate Answer via RAG Chain
    system_prompt = """You are a helpful AI Assistant for a Hospital Medical Shop.
    Use the following pieces of context (medicine data) to answer the user's question.
    
    RULES:
    1. If the user asks for a medicine, check its 'Stock Status'.
    2. If 'Stock Status' is 'No', explicitly state it is OUT OF STOCK and suggest the 'Alternative' listed in the context.
    3. Provide Dosage Instructions and Side Effects if asked or relevant.
    4. If the answer is not in the context, say "I don't have information on that medicine."
    5. Always be professional and concise.

    Context:
    {context}"""
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}"),
    ])
    
    chain = prompt | llm | StrOutputParser()
    
    # Stream the final response
    return chain.stream({
        "context": context,
        "chat_history": chat_history,
        "question": standalone_question
    })

# Kept for backward compatibility and test script runner
def get_rag_chain():
    """Initializes the RAG chain using LCEL (Stateless, fallback)."""
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vectordb = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
    retriever = vectordb.as_retriever(search_kwargs={"k": 3})
    llm = ChatOllama(model=MODEL_NAME, temperature=0.1)
    
    template = """You are a helpful AI Assistant for a Hospital Medical Shop.
    Use the following pieces of context (medicine data) to answer the user's question.
    
    RULES:
    1. If the user asks for a medicine, check its 'Stock Status'.
    2. If 'Stock Status' is 'No', explicitly state it is OUT OF STOCK and suggest the 'Alternative' listed in the context.
    3. Provide Dosage Instructions and Side Effects if asked or relevant.
    4. If the answer is not in the context, say "I don't have information on that medicine."
    5. Always be professional and concise.

    Context:
    {context}

    Question: {question}

    Helpful Answer:"""
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", template),
        ("human", "{question}"),
    ])
    
    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)
        
    class DirectHybridRetriever:
        def __init__(self, df, retriever):
            self.df = df
            self.retriever = retriever
            
        def __call__(self, question):
            return get_hybrid_context(question, self.df, self.retriever)

    df = pd.read_csv(DATA_PATH)
    hybrid_retriever = DirectHybridRetriever(df, retriever)

    # Simple stateless chain matching original structure but with hybrid retrieval
    rag_chain = (
        {"context": lambda q: hybrid_retriever(q), "chat_history": lambda _: [], "question": lambda x: x}
        | prompt
        | llm
        | StrOutputParser()
    )
    return rag_chain

if __name__ == "__main__":
    # Test run
    # uncomment build_vectorstore() if you need to rebuild
    # build_vectorstore()
    print("Initializing Chain...")
    try:
        chain = get_rag_chain()
        res = chain.invoke("Do you have Ibuprofen?")
        print("Response:", res)
    except Exception as e:
        print(f"Error: {e}")
