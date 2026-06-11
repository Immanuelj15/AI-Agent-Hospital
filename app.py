# app.py
import streamlit as st
import os
import pandas as pd
from rag_agent import build_vectorstore, stream_rag_response, DATA_PATH
from langchain_core.messages import HumanMessage, AIMessage

# Page Config
st.set_page_config(page_title="MediBot - AI Hospital Assistant", page_icon="💊", layout="wide")

# Custom CSS
st.markdown("""
<style>
    .chat-message {
        padding: 1.5rem; border-radius: 0.5rem; margin-bottom: 1rem; display: flex
    }
    .chat-message.user {
        background-color: #2b313e
    }
    .chat-message.bot {
        background-color: #475063
    }
    .stButton>button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3063/3063823.png", width=100)
    st.title("🏥 MediBot Settings")
    st.markdown("---")
    
    if st.button("🔄 Rebuild Medicine Database"):
        with st.spinner("Updating Knowledge Base..."):
            try:
                build_vectorstore()
                st.success("Database Updated Successfully!")
            except Exception as e:
                st.error(f"Error updating DB: {e}")
                st.info("Make sure Ollama is running.")

    st.markdown("---")
    st.write("### 📊 Database Preview")
    if os.path.exists(DATA_PATH):
        df = pd.read_csv(DATA_PATH)
        st.dataframe(df.head(10), hide_index=True)
    else:
        st.error("medicines.csv not found!")

# Main Content
st.title("💊 AI Agent for Hospital & Medical Shop")
st.markdown("Ask about **Medicine Stock**, **Alternatives**, **Dosage**, or **Side Effects**.")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display prior chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ex: 'Do you have Ibuprofen?' or 'What is the dosage for Amoxicillin?'"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        # Convert streamlit session history to LangChain Message classes
        chat_history = []
        # Exclude the latest user message which was just appended
        for msg in st.session_state.messages[:-1]:
            if msg["role"] == "user":
                chat_history.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                chat_history.append(AIMessage(content=msg["content"]))

        try:
            with st.spinner("Consulting Medical Database..."):
                response_stream = stream_rag_response(prompt, chat_history)
            
            # Stream response chunks to UI
            response = st.write_stream(response_stream)
            st.session_state.messages.append({"role": "assistant", "content": response})
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            if "Connection refused" in str(e):
                error_msg = "🚨 **Connection Error**: Could not connect to Ollama. Please ensure `ollama serve` is running."
            st.error(error_msg)
