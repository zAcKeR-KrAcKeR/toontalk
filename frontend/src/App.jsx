import { useEffect, useRef, useState } from 'react'
import VideoPlayer from './components/VideoPlayer'
import ProcessingState from './components/ProcessingState'
import {
  uploadVideo, uploadFromUrl, processVideo,
  subscribeToStatus, listVideos, getVideo, stopSandbox,
} from './services/api'

async function cloneVoicesApi(videoId, collectionId) {
  const res = await fetch(`/api/clone-voices/${videoId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      collection_id: collectionId,
      characters: [], // Empty list triggers auto-detection in backend
    }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ── Screens ──────────────────────────────────────────────────────────────────
const SCREEN = { HOME: 'home', UPLOAD: 'upload', PROCESSING: 'processing', WATCH: 'watch', LIBRARY: 'library' }

const CHARACTER_EMOJIS = { shinchan: '🟠', generic: '🎭' }

export default function App() {
  const [screen, setScreen] = useState(SCREEN.HOME)
  const [video, setVideo] = useState(null)
  const [processingStatus, setProcessingStatus] = useState(null)
  const [library, setLibrary] = useState([])
  const [uploading, setUploading] = useState(false)
  const [urlInput, setUrlInput] = useState('')
  const [titleInput, setTitleInput] = useState('')
  const [titleError, setTitleError] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [error, setError] = useState(null)
  const fileInputRef = useRef(null)
  const unsubRef = useRef(null)

  // Load library on mount
  useEffect(() => {
    listVideos().then(setLibrary).catch(() => {})
  }, [])


  // ── Upload handlers ────────────────────────────────────────────────────────

  const handleFile = async (file) => {
    if (!file) return
    if (!titleInput.trim()) { setTitleError(true); return }
    setTitleError(false)
    setError(null)
    setUploading(true)
    setScreen(SCREEN.UPLOAD)
    try {
      const meta = await uploadVideo(file, titleInput.trim())
      await startProcessing(meta)
    } catch (e) {
      setError(e.message)
      setUploading(false)
    }
  }

  const handleUrl = async () => {
    if (!urlInput.trim()) return
    if (!titleInput.trim()) { setTitleError(true); return }
    setTitleError(false)
    setError(null)
    setUploading(true)
    setScreen(SCREEN.UPLOAD)
    try {
      const meta = await uploadFromUrl(urlInput.trim(), titleInput.trim())
      await startProcessing(meta)
    } catch (e) {
      setError(e.message)
      setUploading(false)
    }
  }

  const startProcessing = async (meta) => {
    setUploading(false)
    setScreen(SCREEN.PROCESSING)
    setProcessingStatus({ event: 'started', message: '🚀 Starting ToonTalk AI pipeline...', progress: 5 })

    const { job_id, video_id } = await processVideo(meta.video_id, ['shinchan', 'doraemon', 'nobita'])

    unsubRef.current = subscribeToStatus(
      job_id,
      (status) => setProcessingStatus(status),
      async (status) => {
        // Done — load full video data
        const fullVideo = await getVideo(video_id)
        setVideo(fullVideo)
        setLibrary(prev => [...prev.filter(v => v.video_id !== video_id), fullVideo])
        setScreen(SCREEN.WATCH)
      },
      (err) => {
        setError(err.message)
        setProcessingStatus(prev => ({ ...prev, event: 'error', message: '❌ ' + err.message }))
      }
    )
  }

  const handleWatchVideo = async (v) => {
    try {
      const full = await getVideo(v.video_id)
      setVideo(full)
      setScreen(SCREEN.WATCH)
    } catch (e) {
      setError(e.message)
    }
  }

  const handleCloneVoices = async (v, e) => {
    e.stopPropagation()  // don't open Watch & Chat
    setError(null)
    try {
      const { job_id } = await cloneVoicesApi(v.video_id, v.collection_id)
      setScreen(SCREEN.PROCESSING)
      setProcessingStatus({ event: 'started', message: '🎤 Starting voice cloning...', progress: 5 })
      unsubRef.current = subscribeToStatus(
        job_id,
        (s) => setProcessingStatus(s),
        async () => {
          const updated = await getVideo(v.video_id)
          setLibrary(prev => [...prev.filter(x => x.video_id !== v.video_id), updated])
          setScreen(SCREEN.LIBRARY)
        },
        (err) => setError('Voice cloning failed: ' + err.message)
      )
    } catch (e) {
      setError(e.message)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)  // handleFile checks title internally
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="app">
      {/* ── Navbar ── */}
      <nav className="navbar">
        <span className="logo" onClick={() => setScreen(SCREEN.HOME)} style={{ cursor: 'pointer' }}>
          Toon<span>Talk</span> 🎬
        </span>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <button className="btn btn-secondary" style={{ fontSize: '0.85rem' }}
            onClick={() => setScreen(SCREEN.LIBRARY)}>
            📚 Library {library.length > 0 ? `(${library.length})` : ''}
          </button>
          <button className="btn btn-primary" style={{ fontSize: '0.85rem' }}
            onClick={() => setScreen(SCREEN.HOME)}>
            ＋ New Cartoon
          </button>
        </div>
      </nav>

      {/* ── Error toast ── */}
      {error && (
        <div style={{
          position: 'fixed', bottom: '1.5rem', right: '1.5rem',
          background: '#1e1010', border: '1px solid #ff4444',
          borderRadius: 12, padding: '0.75rem 1.2rem',
          color: '#ff8888', zIndex: 999, maxWidth: 400,
          display: 'flex', gap: '0.75rem', alignItems: 'center',
        }}>
          <span>❌ {error}</span>
          <button onClick={() => setError(null)} style={{ background: 'none', border: 'none', color: '#ff8888', cursor: 'pointer', fontSize: '1.2rem' }}>×</button>
        </div>
      )}

      {/* ── HOME ── */}
      {screen === SCREEN.HOME && (
        <div className="page-center">
          <div className="page-hero" style={{ maxWidth: 700 }}>
            {/* Floating sparkles */}
            {[...Array(5)].map((_, i) => (
              <div key={i} className="sparkle" style={{
                position: 'fixed',
                left: `${10 + i * 20}%`,
                top: `${20 + (i % 3) * 25}%`,
                animationDelay: `${i * 0.4}s`,
              }} />
            ))}

            <div style={{ fontSize: '4rem', marginBottom: '1rem' }}>🎬</div>
            <h1>Cartoon Characters<br/>Se Baat Karo!</h1>
            <p className="subtitle">
              Apna favourite cartoon upload karo, aur Shinchan, Doraemon ya Nobita se
              seedha sawaal puchho — unki apni awaaz mein!
            </p>

            {/* Title input — required before upload */}
            <div style={{ width: '100%', maxWidth: 520, marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontWeight: 700, fontSize: '0.9rem', marginBottom: '0.4rem', color: 'var(--text-secondary)' }}>
                📝 Video ka title likho <span style={{ color: '#ff6b6b' }}>*</span>
              </label>
              <input
                className="text-input"
                placeholder="e.g. Shinchan Episode 5 - Candy Store"
                value={titleInput}
                onChange={(e) => { setTitleInput(e.target.value); setTitleError(false) }}
                style={{
                  width: '100%',
                  border: titleError ? '2px solid #ff6b6b' : undefined,
                  boxShadow: titleError ? '0 0 0 3px rgba(255,107,107,0.2)' : undefined,
                }}
              />
              {titleError && (
                <p style={{ color: '#ff6b6b', fontSize: '0.78rem', marginTop: '0.3rem' }}>
                  ⚠️ Title required hai — pehle title likho phir upload karo
                </p>
              )}
            </div>

            {/* Upload zone */}
            <div
              className={`upload-zone ${dragOver ? 'drag-over' : ''}`}
              style={{ width: '100%', maxWidth: 520 }}
              onDrop={handleDrop}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onClick={() => fileInputRef.current?.click()}
            >
              <span className="upload-icon">📁</span>
              <h3>Cartoon ka video yahan drop karo</h3>
              <p>MP4 format — Shinchan, Doraemon, koi bhi!</p>
              <input ref={fileInputRef} type="file" accept="video/*" hidden
                onChange={(e) => handleFile(e.target.files[0])} />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', margin: '1rem 0', width: '100%', maxWidth: 520 }}>
              <div className="divider" style={{ flex: 1 }} />
              <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>ya URL se</span>
              <div className="divider" style={{ flex: 1 }} />
            </div>

            {/* URL input */}
            <div style={{ display: 'flex', gap: '0.75rem', width: '100%', maxWidth: 520 }}>
              <input
                className="text-input"
                placeholder="YouTube ya direct video URL..."
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleUrl()}
              />
              <button className="btn btn-accent" onClick={handleUrl} disabled={!urlInput.trim()}>
                Upload
              </button>
            </div>

            {/* Features */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginTop: '2.5rem', width: '100%', maxWidth: 520 }}>
              {[
                { icon: '🎬', title: 'AI Scene Analysis', desc: 'VLM scene samajhta hai' },
                { icon: '🎤', title: 'Voice Cloning', desc: 'Original character ki awaaz' },
                { icon: '💬', title: 'Manga Bubbles', desc: 'Authentic comic style' },
              ].map(f => (
                <div key={f.title} className="card" style={{ padding: '1rem', textAlign: 'center' }}>
                  <div style={{ fontSize: '1.8rem', marginBottom: '0.4rem' }}>{f.icon}</div>
                  <div style={{ fontWeight: 800, fontSize: '0.85rem', marginBottom: '0.2rem' }}>{f.title}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{f.desc}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── UPLOAD (uploading indicator) ── */}
      {screen === SCREEN.UPLOAD && (
        <div className="page-center">
          <div style={{ textAlign: 'center' }}>
            <div className="loading-ring" style={{ width: 64, height: 64, borderWidth: 6, margin: '0 auto 1.5rem' }} />
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.5rem' }}>
              Video upload ho rahi hai...
            </h2>
            <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
              Bas thodi der mein AI processing shuru hogi!
            </p>
          </div>
        </div>
      )}

      {/* ── PROCESSING ── */}
      {screen === SCREEN.PROCESSING && (
        <div className="page-center">
          <div style={{ width: '100%', maxWidth: 480 }}>
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.8rem', marginBottom: '1.5rem', textAlign: 'center' }}>
              🤖 ToonTalk AI kaam kar raha hai...
            </h2>
            <ProcessingState status={processingStatus} />
            <div className="stream-notice" style={{ marginTop: '1rem' }}>
              ℹ️ Pehli baar processing mein 5-15 minute lagte hain. Dusri baar instant hoga!
            </div>
          </div>
        </div>
      )}

      {/* ── WATCH ── */}
      {screen === SCREEN.WATCH && video && (
        <div className="main-layout">
          {/* Main player */}
          <div>
            <VideoPlayer video={video} />
          </div>

          {/* Sidebar */}
          <div className="sidebar">
            {/* Video info */}
            <div className="card" style={{ padding: '1.2rem' }}>
              <div className="section-title">Episode Info</div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '1.1rem', marginBottom: '0.5rem' }}>
                {video.name}
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <span className="tag tag-success">✅ Ready</span>
                {video.scene_index_id && <span className="tag tag-info">🎬 Scene Index</span>}
                {video.spoken_word_indexed && <span className="tag tag-info">🗣️ Dialogue</span>}
              </div>
            </div>

            {/* Characters available */}
            {video.character_voices && Object.keys(video.character_voices).length > 0 && (
              <div className="card" style={{ padding: '1.2rem' }}>
                <div className="section-title">Available Characters</div>
                <div className="character-grid">
                  {Object.keys(video.character_voices).map(char => (
                    <div key={char} className="character-card">
                      <span className="char-emoji">{CHARACTER_EMOJIS[char] || '🎭'}</span>
                      <div className="char-name">{char}</div>
                      <div style={{ fontSize: '0.65rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                        Voice cloned ✓
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* How to use */}
            <div className="card" style={{ padding: '1.2rem' }}>
              <div className="section-title">Kaise Use Karein?</div>
              {[
                { n: '1', t: 'Video dekhte rehna', d: 'Jo scene pasand aaye wahaan ruk jao' },
                { n: '2', t: 'Mic press karo 🎙️', d: 'Video automatically pause ho jaayegi' },
                { n: '3', t: 'Sawaal puchho', d: 'Hindi ya English mein, character se' },
                { n: '4', t: 'Answer suno', d: 'Character apni awaaz mein jawab dega!' },
              ].map(s => (
                <div key={s.n} style={{ display: 'flex', gap: '0.75rem', marginBottom: '0.75rem', alignItems: 'flex-start' }}>
                  <div style={{
                    background: 'var(--primary)', color: 'white', borderRadius: '50%',
                    width: 24, height: 24, display: 'flex', alignItems: 'center',
                    justifyContent: 'center', fontSize: '0.75rem', fontWeight: 800, flexShrink: 0,
                  }}>{s.n}</div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.85rem' }}>{s.t}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{s.d}</div>
                  </div>
                </div>
              ))}
            </div>

            {/* Save credits button */}
            <button className="btn btn-secondary" style={{ width: '100%', fontSize: '0.8rem' }}
              onClick={() => stopSandbox().then(() => alert('Sandbox stopped. Credits saved! 💰'))}>
              💰 Sandbox stop karo (credits bachao)
            </button>
          </div>
        </div>
      )}

      {/* ── LIBRARY ── */}
      {screen === SCREEN.LIBRARY && (
        <div style={{ padding: '2rem', maxWidth: 900, margin: '0 auto' }}>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.8rem', marginBottom: '1.5rem' }}>
            📚 My Cartoon Library
          </h2>

          {library.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-secondary)' }}>
              <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>📭</div>
              <p>Abhi koi cartoon nahi hai. Upload karo!</p>
              <button className="btn btn-primary" style={{ marginTop: '1rem' }}
                onClick={() => setScreen(SCREEN.HOME)}>
                + Upload Cartoon
              </button>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1.2rem' }}>
              {library.map(v => (
                <div key={v.video_id} className="card" style={{ padding: '1.2rem', cursor: 'pointer' }}
                  onClick={() => handleWatchVideo(v)}>
                  <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem', textAlign: 'center' }}>📺</div>
                  <div style={{ fontWeight: 800, fontFamily: 'var(--font-display)', fontSize: '1rem', marginBottom: '0.4rem' }}>
                    {v.name}
                  </div>
                  <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
                    {v.processing_status === 'ready' && <span className="tag tag-success">✅ Ready</span>}
                    {v.scene_index_id && <span className="tag tag-info">🎬</span>}
                    {v.spoken_word_indexed && <span className="tag tag-info">🗣️</span>}
                    {v.character_voices && Object.keys(v.character_voices).length > 0 && (
                      <span className="tag tag-primary">
                        🎤 {Object.keys(v.character_voices).length} voices
                      </span>
                    )}
                  </div>
                  {/* Clone Voices button — shown when indexed but no voices yet */}
                  {v.spoken_word_indexed && (!v.character_voices || Object.keys(v.character_voices).length === 0) && (
                    <button
                      className="btn btn-secondary"
                      style={{ width: '100%', fontSize: '0.82rem', marginBottom: '0.5rem' }}
                      onClick={(e) => handleCloneVoices(v, e)}
                    >
                      🎤 Clone Character Voices
                    </button>
                  )}
                  <button className="btn btn-primary" style={{ width: '100%', fontSize: '0.85rem' }}
                    onClick={() => handleWatchVideo(v)}>
                    ▶ Watch &amp; Chat
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
