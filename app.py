from rag_agent import build_vectorstore, query_agent
import streamlit as st
import os

st.set_page_config(page_title="AI Medical Agent", layout="wide")

st.title("💊 AI Agent for Hospital & Medical Shop")

vectordb = None
if os.path.exists("chroma_store"):
    st.success("✅ Vector Database Loaded!")
    from langchain_community.vectorstores import Chroma
    from langchain_community.embeddings import OllamaEmbeddings
    vectordb = Chroma(persist_directory="chroma_store", embedding_function=OllamaEmbeddings(model="mistral"))
else:
    with st.spinner("Building vector database..."):
        vectordb = build_vectorstore("medicines.csv")

option = st.sidebar.radio("Choose Service", ["💉 Medicine Availability Check", "🧾 Tablet Prescription", "📘 Tablet Usage"])

query = st.text_input("Ask your medical question:", placeholder="e.g. Do you have Paracetamol 500mg?")

if st.button("Ask AI"):
    if query:
        with st.spinner("Thinking..."):
            answer = query_agent(query, vectordb)
        st.subheader("🩺 AI Response")
        st.write(answer)
    else:
        st.warning("Please enter a query.")
