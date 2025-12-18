# rag_agent.py
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.llms import Ollama
from langchain.chains import RetrievalQA
from langchain.text_splitter import CharacterTextSplitter
from langchain.schema import Document
import pandas as pd
import os

# -------------------------
# Load and Prepare Data
# -------------------------
def load_medicine_data(csv_path):
    df = pd.read_csv(csv_path)
    docs = []
    for _, row in df.iterrows():
        content = (
            f"Medicine Name: {row['Medicine_Name']}\n"
            f"Strength: {row['Strength']}\n"
            f"Use Case: {row['Use_Case']}\n"
            f"Alternative: {row['Alternative']}\n"
            f"Stock: {row['Stock']}\n"
            f"Dosage Instruction: {row['Dosage_Instruction']}\n"
        )
        docs.append(Document(page_content=content))
    return docs


# -------------------------
# Build or Load Vector Store
# -------------------------
def build_vectorstore(csv_path="medicines.csv", persist_dir="chroma_store"):
    os.makedirs(persist_dir, exist_ok=True)

    embeddings = OllamaEmbeddings(model="mistral")
    docs = load_medicine_data(csv_path)

    text_splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    split_docs = text_splitter.split_documents(docs)

    vectordb = Chroma.from_documents(split_docs, embedding=embeddings, persist_directory=persist_dir)
    vectordb.persist()
    return vectordb


# -------------------------
# Query the Agent
# -------------------------
def query_agent(user_query, vectordb):
    llm = Ollama(model="mistral")
    retriever = vectordb.as_retriever(search_kwargs={"k": 3})
    qa = RetrievalQA.from_chain_type(llm=llm, retriever=retriever, chain_type="stuff")
    response = qa.run(user_query)
    return response
