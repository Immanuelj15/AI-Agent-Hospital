// frontend/src/App.jsx
import React, { useState, useEffect, useRef } from 'react'

let API_BASE = import.meta.env.VITE_API_BASE || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? 'http://127.0.0.1:8000' : '');
if (API_BASE.endsWith('/')) {
  API_BASE = API_BASE.slice(0, -1);
}

function App() {
  const [activeTab, setActiveTab] = useState('dashboard')

  // --- Role / Authentication States ---
  const [userRole, setUserRole] = useState('clerk') // 'clerk' or 'doctor'

  // --- Dashboard States ---
  const [stats, setStats] = useState(null)
  const [loadingStats, setLoadingStats] = useState(false)

  // --- Directory States ---
  const [medicines, setMedicines] = useState([])
  const [totalMedicines, setTotalMedicines] = useState(0)
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [classification, setClassification] = useState('')
  const [page, setPage] = useState(1)
  const [loadingMedicines, setLoadingMedicines] = useState(false)
  const [expandedMedicine, setExpandedMedicine] = useState(null)

  // --- Chat States ---
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Welcome to AyuReg Clinical Intelligence Assistant. Ask me about medicine indications, dosages, side effects, stock availability, and treatment guidelines.' }
  ])
  const [chatInput, setChatInput] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)
  const chatEndRef = useRef(null)

  // --- Guidelines List ---
  const guidelines = [
    { title: "Antibiotic Safety Protocols", prompt: "Explain the antibiotic usage guidelines and when they are recommended." },
    { title: "Viral Replication Control", prompt: "What are the treatment protocols for viral outbreaks?" },
    { title: "Type 2 Diabetes Registry", prompt: "What are the first-line therapies and side effects for antidiabetic agents?" },
    { title: "Fungal Infection Treatments", prompt: "How are localized fungal infections managed?" },
    { title: "Fever Management Limits", prompt: "What are the recommended guidelines for antipyretic administration?" }
  ]

  // --- Guidelines Uploader States ---
  const [uploading, setUploading] = useState(false)
  const [uploadStatus, setUploadStatus] = useState('')

  // --- Global Rebuild State ---
  const [rebuilding, setRebuilding] = useState(false)
  const [rebuildStatus, setRebuildStatus] = useState('')

  // Scroll chat to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Fetch Stats on mount
  useEffect(() => {
    fetchStats()
  }, [])

  // Fetch medicines when filters/page change
  useEffect(() => {
    fetchMedicines()
  }, [page, category, classification])

  const fetchStats = async () => {
    setLoadingStats(true)
    try {
      const res = await fetch(`${API_BASE}/api/stats`)
      if (res.ok) {
        const data = await res.json()
        setStats(data)
      }
    } catch (err) {
      console.error("Error fetching stats:", err)
    } finally {
      setLoadingStats(false)
    }
  }

  const fetchMedicines = async (resetPage = false) => {
    setLoadingMedicines(true)
    const currentPage = resetPage ? 1 : page
    if (resetPage) setPage(1)
    
    let url = `${API_BASE}/api/medicines?page=${currentPage}&limit=15`
    if (search) url += `&search=${encodeURIComponent(search)}`
    if (category) url += `&category=${encodeURIComponent(category)}`
    if (classification) url += `&classification=${encodeURIComponent(classification)}`

    try {
      const res = await fetch(url)
      if (res.ok) {
        const data = await res.json()
        setMedicines(data.data)
        setTotalMedicines(data.total)
      }
    } catch (err) {
      console.error("Error fetching medicines:", err)
    } finally {
      setLoadingMedicines(false)
    }
  }

  const handleRebuild = async () => {
    if (!window.confirm("Do you want to reindex the SQLite database and rebuild the guidelines vector store? This processes all 50k rows.")) return
    setRebuilding(true)
    setRebuildStatus('Processing...')
    try {
      const res = await fetch(`${API_BASE}/api/rebuild`, { method: 'POST' })
      if (res.ok) {
        setRebuildStatus('Success!')
        alert("Database and vector guidelines successfully rebuilt!")
        fetchStats()
        fetchMedicines(true)
      } else {
        setRebuildStatus('Failed')
      }
    } catch (err) {
      setRebuildStatus('Error')
      console.error(err)
    } finally {
      setRebuilding(false)
    }
  }

  // File Upload Handler
  const handleFileUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return

    setUploading(true)
    setUploadStatus('Uploading...')
    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await fetch(`${API_BASE}/api/upload`, {
        method: 'POST',
        body: formData
      })
      const data = await res.json()
      if (res.ok) {
        setUploadStatus('Success!')
        alert(`Guidelines file "${file.name}" successfully parsed and indexed!`)
        // Add system message to chat
        setMessages(prev => [...prev, { role: 'system', content: `Indexed clinical guidelines from file: ${file.name}` }])
      } else {
        setUploadStatus(`Error: ${data.detail}`)
      }
    } catch (err) {
      setUploadStatus('Upload Failed')
      console.error(err)
    } finally {
      setUploading(false)
    }
  }

  // Conversational Streaming RAG Chat
  const handleSendMessage = async (e, customPrompt = null) => {
    e?.preventDefault()
    const promptToSend = customPrompt || chatInput
    if (!promptToSend.trim() || isGenerating) return

    if (!customPrompt) setChatInput('')
    
    // Add user message
    const updatedMessages = [...messages, { role: 'user', content: promptToSend }]
    setMessages(updatedMessages)
    setIsGenerating(true)

    // Add temporary empty assistant message to write into
    setMessages(prev => [...prev, { role: 'assistant', content: '' }])

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: promptToSend,
          chat_history: updatedMessages.slice(0, -1), // Exclude current question
          role: userRole
        })
      })

      if (!response.ok) {
        const errData = await response.json()
        throw new Error(errData.detail || "Server Error")
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let done = false
      let fullText = ""

      while (!done) {
        const { value, done: readerDone } = await reader.read()
        done = readerDone
        if (value) {
          const chunk = decoder.decode(value, { stream: !done })
          fullText += chunk
          
          // Update the last assistant message in real time
          setMessages(prev => {
            const copy = [...prev]
            if (copy.length > 0) {
              copy[copy.length - 1] = { role: 'assistant', content: fullText }
            }
            return copy
          })
        }
      }
    } catch (err) {
      console.error(err)
      setMessages(prev => {
        const copy = [...prev]
        if (copy.length > 0) {
          copy[copy.length - 1] = { role: 'assistant', content: `Error: ${err.message}. Make sure the backend FastAPI server is running.` }
        }
        return copy
      })
    } finally {
      setIsGenerating(false)
    }
  }

  return (
    <div id="root">
      {/* Navbar Header */}
      <header className="navbar">
        <div className="logo-container">
          <div className="logo-indicator"></div>
          <div className="logo-text">Ayu<span>Reg</span></div>
          <div className="logo-badge">ICMR</div>
        </div>
        
        {/* Role Toggle switches in Nav */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', border: '1px solid var(--border)', padding: '3px', borderRadius: '20px', backgroundColor: 'rgba(0,0,0,0.2)' }}>
          <button 
            className="btn" 
            onClick={() => setUserRole('clerk')}
            style={{ 
              borderRadius: '16px', 
              fontSize: '0.75rem', 
              padding: '0.35rem 0.85rem', 
              backgroundColor: userRole === 'clerk' ? 'rgba(14, 165, 233, 0.15)' : 'transparent',
              color: userRole === 'clerk' ? 'var(--clerk-theme)' : 'var(--text)',
              border: userRole === 'clerk' ? '1px solid rgba(14, 165, 233, 0.3)' : '1px solid transparent',
              fontWeight: '700'
            }}
          >
            Clerk Access
          </button>
          <button 
            className="btn" 
            onClick={() => setUserRole('doctor')}
            style={{ 
              borderRadius: '16px', 
              fontSize: '0.75rem', 
              padding: '0.35rem 0.85rem', 
              backgroundColor: userRole === 'doctor' ? 'rgba(139, 92, 246, 0.15)' : 'transparent',
              color: userRole === 'doctor' ? 'var(--doctor-theme)' : 'var(--text)',
              border: userRole === 'doctor' ? '1px solid rgba(139, 92, 246, 0.3)' : '1px solid transparent',
              fontWeight: '700'
            }}
          >
            Doctor Access
          </button>
        </div>

        <nav className="nav-tabs">
          <button 
            className={`nav-tab ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => setActiveTab('dashboard')}
          >
            Dashboard
          </button>
          <button 
            className={`nav-tab ${activeTab === 'directory' ? 'active' : ''}`}
            onClick={() => setActiveTab('directory')}
          >
            Medicine Directory
          </button>
          <button 
            className={`nav-tab ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
          >
            Clinical Assistant
          </button>
        </nav>

        <div>
          <button 
            className="btn btn-outline" 
            onClick={handleRebuild}
            disabled={rebuilding}
            style={{ fontSize: '0.82rem', padding: '0.4rem 0.8rem' }}
          >
            {rebuilding ? 'Rebuilding...' : 'Rebuild Registry'}
          </button>
          {rebuildStatus && <span style={{ fontSize: '0.75rem', marginLeft: '0.5rem', color: rebuildStatus.includes('Success') ? 'var(--success)' : 'var(--text)' }}>{rebuildStatus}</span>}
        </div>
      </header>

      {/* Main Container Area */}
      <main className="main-content">
        
        {/* TAB 1: ANALYTICS DASHBOARD */}
        {activeTab === 'dashboard' && (
          <>
            <div className="dashboard-grid">
              <div className="stat-card">
                <div className="stat-header">Total Registry Medicines</div>
                <div className="stat-value">{stats ? stats.total.toLocaleString() : '50,000'}</div>
                <div className="stat-desc">Indexed from CSV Dataset</div>
              </div>
              <div className="stat-card">
                <div className="stat-header">Prescription Required</div>
                <div className="stat-value" style={{ color: 'var(--danger)' }}>
                  {stats ? (stats.classifications['Prescription'] || 0).toLocaleString() : '25,000'}
                </div>
                <div className="stat-desc">Rx Class Medications</div>
              </div>
              <div className="stat-card">
                <div className="stat-header">Over-the-Counter (OTC)</div>
                <div className="stat-value" style={{ color: 'var(--success)' }}>
                  {stats ? (stats.classifications['Over-the-Counter'] || 0).toLocaleString() : '25,000'}
                </div>
                <div className="stat-desc">Direct Dispensable Drugs</div>
              </div>
              <div className="stat-card">
                <div className="stat-header">Guidelines Indexed</div>
                <div className="stat-value" style={{ color: 'var(--primary)' }}>{messages.filter(m => m.role === 'system').length + 8}</div>
                <div className="stat-desc">Treatment Guidelines</div>
              </div>
            </div>

            <div className="dashboard-sections">
              <div className="panel-card">
                <h3 className="panel-title">Medicine Categories Split</h3>
                {stats ? (
                  <div className="chart-container" style={{ flexDirection: 'column', gap: '1rem' }}>
                    {stats.categories.map((c, i) => (
                      <div key={i} style={{ width: '100%' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '0.25rem' }}>
                          <span style={{ fontWeight: '600' }}>{c.category}</span>
                          <span>{c.count.toLocaleString()} ({((c.count / stats.total) * 100).toFixed(1)}%)</span>
                        </div>
                        <div style={{ width: '100%', height: '8px', backgroundColor: '#f1f5f9', borderRadius: '4px', overflow: 'hidden' }}>
                          <div style={{ width: `${(c.count / stats.total) * 100}%`, height: '100%', backgroundColor: `hsl(${200 + i * 20}, 75%, 55%)` }}></div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="spinner-wrapper"><div className="spinner"></div></div>
                )}
              </div>

              <div className="panel-card">
                <h3 className="panel-title">Top Manufacturers Profile</h3>
                {stats ? (
                  <div className="chart-container" style={{ flexDirection: 'column', gap: '1rem' }}>
                    {stats.manufacturers.map((m, i) => (
                      <div key={i} style={{ width: '100%' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '0.25rem' }}>
                          <span style={{ fontWeight: '600' }}>{m.manufacturer}</span>
                          <span>{m.count.toLocaleString()}</span>
                        </div>
                        <div style={{ width: '100%', height: '8px', backgroundColor: '#f1f5f9', borderRadius: '4px', overflow: 'hidden' }}>
                          <div style={{ width: `${(m.count / stats.manufacturers[0].count) * 100}%`, height: '100%', backgroundColor: `hsl(${140 + i * 15}, 70%, 50%)` }}></div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="spinner-wrapper"><div className="spinner"></div></div>
                )}
              </div>
            </div>
          </>
        )}

        {/* TAB 2: MEDICINE DIRECTORY */}
        {activeTab === 'directory' && (
          <>
            <div className="search-controls">
              <div className="search-input-wrapper">
                <input 
                  type="text" 
                  className="search-input"
                  placeholder="FTS5 Search: e.g. 'Roche Antidiabetic' or 'Amoxicillin Tablet'..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && fetchMedicines(true)}
                />
              </div>
              
              <select 
                className="filter-select"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                <option value="">All Categories</option>
                <option value="Antidiabetic">Antidiabetic</option>
                <option value="Antiviral">Antiviral</option>
                <option value="Antibiotic">Antibiotic</option>
                <option value="Antifungal">Antifungal</option>
                <option value="Antipyretic">Antipyretic</option>
                <option value="Antidepressant">Antidepressant</option>
                <option value="Analgesic">Analgesic</option>
                <option value="Antiseptic">Antiseptic</option>
              </select>

              <select 
                className="filter-select"
                value={classification}
                onChange={(e) => setClassification(e.target.value)}
              >
                <option value="">All Classifications</option>
                <option value="Prescription">Prescription (Rx)</option>
                <option value="Over-the-Counter">Over-the-Counter (OTC)</option>
              </select>

              <button className="btn btn-primary" onClick={() => fetchMedicines(true)}>
                Apply FTS Search
              </button>
              <button 
                className="btn btn-outline"
                onClick={() => {
                  setSearch('')
                  setCategory('')
                  setClassification('')
                  setPage(1)
                  setTimeout(() => fetchMedicines(true), 50)
                }}
              >
                Reset Filters
              </button>
            </div>

            {loadingMedicines ? (
              <div className="spinner-wrapper"><div className="spinner"></div></div>
            ) : (
              <>
                <div className="table-wrapper">
                  <table className="clinical-table">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Name</th>
                        <th>Category</th>
                        <th>Form</th>
                        <th>Strength</th>
                        <th>Manufacturer</th>
                        <th>Classification</th>
                        <th>Price</th>
                        <th>Stock Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {medicines.map((m) => (
                        <React.Fragment key={m.id}>
                          <tr 
                            onClick={() => setExpandedMedicine(expandedMedicine === m.id ? null : m.id)}
                            style={{ cursor: 'pointer', backgroundColor: expandedMedicine === m.id ? '#f0f9ff' : 'transparent' }}
                          >
                            <td>#{m.id}</td>
                            <td style={{ fontWeight: '600', color: 'var(--text-heading)' }}>
                              {m.name}
                            </td>
                            <td>{m.category}</td>
                            <td>{m.dosage_form}</td>
                            <td>{m.strength}</td>
                            <td>{m.manufacturer}</td>
                            <td>
                              <span className={`badge ${m.classification === 'Prescription' ? 'badge-danger' : 'badge-success'}`}>
                                {m.classification}
                              </span>
                            </td>
                            <td style={{ fontWeight: '700' }}>${m.price.toFixed(2)}</td>
                            <td>
                              <span className={`badge ${m.stock === 'Yes' ? 'badge-success' : 'badge-danger'}`}>
                                {m.stock === 'Yes' ? 'In Stock' : 'Out of Stock'}
                              </span>
                            </td>
                          </tr>
                          {expandedMedicine === m.id && (
                            <tr>
                              <td colSpan="9" className="details-panel">
                                {/* RBAC Lock for Clerk role querying Prescription drug */}
                                {userRole === 'clerk' && m.classification === 'Prescription' ? (
                                  <div className="details-lock-banner">
                                    <h4>Access Restricted (Prescription Rx Medicine)</h4>
                                    <p>
                                      Dispensation and detailed review for <strong>{m.name}</strong> are restricted to licensed clinicians. 
                                      Please switch to <strong>Doctor Access</strong> in the portal header to unlock, or request physician authorization.
                                    </p>
                                  </div>
                                ) : (
                                  <div className="details-grid">
                                    <div className="details-column">
                                      <h4 className="details-section-title">Clinical Indication</h4>
                                      <p style={{ fontSize: '0.9rem' }}>Indicated for treatment and relief in: <strong>{m.indication}</strong></p>
                                      <p style={{ fontSize: '0.9rem', marginTop: '0.5rem' }}>Active Ingredient: <strong style={{ color: 'var(--primary)' }}>{m.active_ingredient}</strong></p>
                                      
                                      <h4 className="details-section-title" style={{ marginTop: '1rem' }}>Dosage Instructions</h4>
                                      <p style={{ fontSize: '0.9rem', color: 'var(--text-heading)' }}>{m.dosage_instruction}</p>
                                      
                                      {userRole === 'doctor' && m.classification === 'Prescription' && (
                                        <button 
                                          className="btn btn-primary" 
                                          onClick={() => alert(`Prescription for ${m.name} successfully authorized and logged in clinician registry.`)}
                                          style={{ marginTop: '1rem', width: 'fit-content', padding: '0.5rem 1rem', fontSize: '0.82rem' }}
                                        >
                                          Authorize & Dispense
                                        </button>
                                      )}
                                    </div>
                                    <div className="details-column">
                                      <h4 className="details-section-title">Potential Side Effects</h4>
                                      <p style={{ fontSize: '0.9rem', color: 'var(--danger)' }}>{m.side_effects}</p>
                                      
                                      <h4 className="details-section-title" style={{ marginTop: '1rem' }}>Recommended Alternative</h4>
                                      <p style={{ fontSize: '0.9rem' }}>
                                        {m.stock === 'No' ? (
                                          <span>Substitute with: <strong style={{ color: 'var(--success)' }}>{m.alternative}</strong> (Available in stock)</span>
                                        ) : (
                                          <span style={{ color: 'var(--text)' }}>Primary medication in stock. No alternative required.</span>
                                        )}
                                      </p>
                                    </div>
                                  </div>
                                )}
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      ))}
                      {medicines.length === 0 && (
                        <tr>
                          <td colSpan="9" style={{ textAlign: 'center', padding: '2rem' }}>No medicines match the search filters.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                <div className="pagination">
                  <div style={{ fontSize: '0.88rem' }}>
                    Showing <strong>{((page - 1) * 15) + 1} - {Math.min(page * 15, totalMedicines)}</strong> of <strong>{totalMedicines.toLocaleString()}</strong> medicines
                  </div>
                  <div className="pagination-buttons">
                    <button 
                      className="btn btn-outline" 
                      onClick={() => setPage(p => Math.max(p - 1, 1))}
                      disabled={page === 1}
                      style={{ padding: '0.4rem 1rem' }}
                    >
                      Previous
                    </button>
                    <span style={{ alignSelf: 'center', padding: '0 1rem', fontWeight: '600' }}>Page {page} of {Math.ceil(totalMedicines / 15)}</span>
                    <button 
                      className="btn btn-outline" 
                      onClick={() => setPage(p => Math.min(p + 1, Math.ceil(totalMedicines / 15)))}
                      disabled={page >= Math.ceil(totalMedicines / 15)}
                      style={{ padding: '0.4rem 1rem' }}
                    >
                      Next
                    </button>
                  </div>
                </div>
              </>
            )}
          </>
        )}

        {/* TAB 3: CLINICAL CHATBOT ASSISTANT */}
        {activeTab === 'chat' && (
          <div className="chat-container-layout">
            
            {/* Guidelines Sidebar with PDF/TXT uploader */}
            <aside className="chat-guidelines">
              <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem', color: 'var(--text-heading)', borderBottom: '1px solid var(--border)', paddingBottom: '0.5rem' }}>
                ICMR Guidelines
              </h3>
              <p style={{ fontSize: '0.8rem', color: 'var(--text)', marginBottom: '0.5rem' }}>
                Select a topic to automatically prompt the Clinical RAG assistant:
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {guidelines.map((g, i) => (
                  <div 
                    key={i} 
                    className="guideline-item"
                    onClick={(e) => handleSendMessage(e, g.prompt)}
                  >
                    <div className="guideline-item-title">{g.title}</div>
                    <div className="guideline-item-excerpt">Click to run clinical RAG analysis.</div>
                  </div>
                ))}
              </div>

              {/* Dynamic Guidelines File Uploader Widget */}
              <div className="upload-widget">
                <h4 className="upload-widget-title">Import Guidelines</h4>
                <p className="upload-widget-desc">Upload clinical PDF or TXT to expand vector database</p>
                <input 
                  type="file" 
                  accept=".pdf,.txt" 
                  id="guideline-file"
                  onChange={handleFileUpload}
                  style={{ display: 'none' }}
                  disabled={uploading}
                />
                <label 
                  htmlFor="guideline-file" 
                  className="btn btn-outline" 
                  style={{ display: 'inline-block', fontSize: '0.75rem', padding: '0.4rem 0.8rem', cursor: 'pointer', opacity: uploading ? 0.6 : 1 }}
                >
                  {uploading ? 'Processing...' : 'Choose File'}
                </label>
                {uploadStatus && (
                  <div 
                    style={{ 
                      fontSize: '0.72rem', 
                      marginTop: '0.5rem', 
                      color: uploadStatus.includes('Success') ? 'var(--success)' : uploadStatus.includes('Uploading') ? 'var(--primary)' : 'var(--danger)' 
                    }}
                  >
                    {uploadStatus}
                  </div>
                )}
              </div>
            </aside>

            {/* Main Chat Panel */}
            <section className="chat-main">
              <div className="chat-header">
                <div>
                  <h3 style={{ margin: 0, fontSize: '1.1rem', color: 'var(--text-heading)' }}>
                    Clinical RAG Assistant <span style={{ fontSize: '0.75rem', verticalAlign: 'middle', border: '1px solid rgba(255,255,255,0.08)', padding: '2px 8px', borderRadius: '12px', marginLeft: '0.5rem', color: userRole === 'doctor' ? 'var(--doctor-theme)' : 'var(--clerk-theme)', backgroundColor: userRole === 'doctor' ? 'rgba(139, 92, 246, 0.1)' : 'rgba(14, 165, 233, 0.1)' }}>
                      {userRole === 'doctor' ? 'Doctor Access' : 'Clerk Access'}
                    </span>
                  </h3>
                  <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-muted)' }}>Powered by SQLite FTS5 & ChromaDB</p>
                </div>
                <button 
                  className="btn btn-outline" 
                  onClick={() => setMessages([{ role: 'assistant', content: 'Welcome to AyuReg Clinical Intelligence Assistant. Ask me about medicine indications, dosages, side effects, stock availability, and treatment guidelines.' }])}
                  style={{ fontSize: '0.8rem', padding: '0.3rem 0.6rem' }}
                >
                  Clear Chat
                </button>
              </div>

              {/* Chat Message Output */}
              <div className="chat-body">
                {messages.map((m, idx) => (
                  <div 
                    key={idx} 
                    className={`chat-bubble ${
                      m.role === 'user' ? 'chat-bubble-user' : 
                      m.role === 'system' ? 'chat-bubble-system' : 'chat-bubble-assistant'
                    }`}
                  >
                    {m.content.split('\n').map((line, i) => {
                      if (line.trim().startsWith('[⚠️ CLINICAL WARNING:') || line.trim().startsWith('[CLINICAL WARNING:')) {
                        const warningText = line.trim()
                          .replace('[⚠️ CLINICAL WARNING:', '')
                          .replace('[CLINICAL WARNING:', '')
                          .replace(']', '');
                        return (
                          <div key={i} className="chat-warning-container">
                            {warningText}
                          </div>
                        )
                      }
                      if (line.trim().startsWith('- ')) {
                        return <li key={i} style={{ marginLeft: '1rem', marginBottom: '0.2rem' }}>{line.trim().substring(2)}</li>
                      }
                      if (line.trim().startsWith('* ')) {
                        return <li key={i} style={{ marginLeft: '1rem', marginBottom: '0.2rem' }}>{line.trim().substring(2)}</li>
                      }
                      if (line.trim().startsWith('###')) {
                        return <h4 key={i} style={{ margin: '0.5rem 0 0.25rem 0', fontWeight: 'bold' }}>{line.trim().substring(3)}</h4>
                      }
                      if (line.trim().startsWith('===')) {
                        return null;
                      }
                      return <p key={i} style={{ margin: '0 0 0.5rem 0' }}>{line}</p>
                    })}
                  </div>
                ))}
                
                {isGenerating && (
                  <div className="chat-bubble chat-bubble-assistant">
                    <span className="streaming-dot"></span>
                    <span className="streaming-dot" style={{ animationDelay: '0.2s' }}></span>
                    <span className="streaming-dot" style={{ animationDelay: '0.4s' }}></span>
                  </div>
                )}
                
                <div ref={chatEndRef} />
              </div>

              {/* Chat Input Area */}
              <form className="chat-input-area" onSubmit={handleSendMessage}>
                <input 
                  type="text" 
                  className="chat-text-input"
                  placeholder={
                    userRole === 'doctor' 
                      ? "Ask clinical guidelines, authorize Rx drugs, check stock..." 
                      : "Search stock, dosage details, check alternatives (Rx access restricted)..."
                  }
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  disabled={isGenerating}
                />
                <button 
                  type="submit" 
                  className="btn btn-primary"
                  disabled={isGenerating || !chatInput.trim()}
                >
                  Send
                </button>
              </form>
            </section>
          </div>
        )}

      </main>
    </div>
  )
}

export default App
