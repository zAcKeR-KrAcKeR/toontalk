import { useEffect, useRef, useState } from 'react'
import MicButton from './MicButton'
import CharacterPopup from './CharacterPopup'
import { askQuestion, askVoice, generateTTS, warmupSandbox, getSandboxStatus, getCharacterImage } from '../services/api'

const CHAR_EMOJIS = {
  shinchan: '🟠', misae: '👩', hiroshi: '👨', himawari: '👶',
  doraemon: '🤖', nobita: '😅', shizuka: '👧', gian: '💪',
  suneo: '😏', nene: '🎀', kazama: '🧠', bo: '🐱', masao: '😊', generic: '🎭',
}

export default function VideoPlayer({ video }) {
  const videoRef = useRef(null)
  const audioRef = useRef(null)

  const [paused,        setPaused]        = useState(false)
  const [currentTime,   setCurrentTime]   = useState(0)
  const [duration,      setDuration]      = useState(0)
  const [asking,        setAsking]        = useState(false)
  const [processing,    setProcessing]    = useState(false)
  const [processingMsg, setProcessingMsg] = useState('')
  const [response,      setResponse]      = useState(null)
  const [audioLoading,  setAudioLoading]  = useState(false)
  const [autoplayBlocked, setAutoplayBlocked] = useState(false)
  const [textQuestion,  setTextQuestion]  = useState('')
  const [error,         setError]         = useState(null)
  const [showControls,  setShowControls]  = useState(true)
  const [sandboxReady,  setSandboxReady]  = useState(false)
  const [charImageUrl,  setCharImageUrl]  = useState(null)
  const controlsTimer = useRef(null)
  const ttsAbortRef   = useRef(null)   // cancel in-flight TTS when new question asked

  const streamUrl = video?.stream_url

  // ── Pre-warm sandbox ──────────────────────────────────────────────────────
  useEffect(() => {
    warmupSandbox()
    const poll = setInterval(async () => {
      const s = await getSandboxStatus()
      if (s?.ready) { setSandboxReady(true); clearInterval(poll) }
    }, 5000)
    setTimeout(async () => {
      const s = await getSandboxStatus()
      if (s?.ready) { setSandboxReady(true); clearInterval(poll) }
    }, 3000)
    return () => clearInterval(poll)
  }, [])

  // ── Auto-hide controls ────────────────────────────────────────────────────
  const revealControls = () => {
    setShowControls(true)
    clearTimeout(controlsTimer.current)
    controlsTimer.current = setTimeout(() => setShowControls(false), 3000)
  }

  // ── Track current time ────────────────────────────────────────────────────
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    const onTime = () => setCurrentTime(v.currentTime)
    const onLoad = () => setDuration(v.duration)
    v.addEventListener('timeupdate', onTime)
    v.addEventListener('loadedmetadata', onLoad)
    return () => {
      v.removeEventListener('timeupdate', onTime)
      v.removeEventListener('loadedmetadata', onLoad)
    }
  }, [])

  // ── Auto-play audio the instant URL arrives ───────────────────────────────
  useEffect(() => {
    const el = audioRef.current
    if (!el || !response?.audio_url) return
    setAutoplayBlocked(false)
    el.pause()
    el.src = response.audio_url
    el.load()
    el.play().catch(() => setAutoplayBlocked(true))
  }, [response?.audio_url])

  // ── Fire background TTS after text arrives ────────────────────────────────
  const fireBackgroundTTS = async (data) => {
    if (!data?.answer_text || !data?.character) return

    // Cancel any in-flight TTS from a previous question
    if (ttsAbortRef.current) ttsAbortRef.current.abort()
    const ctrl = new AbortController()
    ttsAbortRef.current = ctrl

    setAudioLoading(true)
    try {
      const tts = await generateTTS(video.video_id, data.character, data.answer_text, ctrl.signal)
      if (tts?.audio_url) {
        setResponse(prev => prev ? { ...prev, audio_url: tts.audio_url } : prev)
      }
    } catch (err) {
      if (err.name !== 'AbortError') console.error('TTS failed:', err)
    } finally {
      setAudioLoading(false)
    }
  }

  // ── Handlers ──────────────────────────────────────────────────────────────

  const handleAskClick = () => {
    if (videoRef.current) videoRef.current.pause()
    setPaused(true)
    setAsking(true)
    setResponse(null)
    setError(null)
    setAudioLoading(false)
    setAutoplayBlocked(false)
  }

  const handleContinue = () => {
    if (ttsAbortRef.current) { ttsAbortRef.current.abort(); ttsAbortRef.current = null }
    setAsking(false)
    setResponse(null)
    setTextQuestion('')
    setProcessing(false)
    setAudioLoading(false)
    setCharImageUrl(null)
    if (videoRef.current) videoRef.current.play()
    setPaused(false)
  }

  const submitQuestion = async (questionText) => {
    if (!questionText?.trim()) return
    if (ttsAbortRef.current) { ttsAbortRef.current.abort(); ttsAbortRef.current = null }
    setProcessing(true)
    setProcessingMsg('Scene dekh raha hai... 🎬')
    setError(null)
    setResponse(null)
    setCharImageUrl(null)
    setAudioLoading(false)
    const t1 = setTimeout(() => setProcessingMsg('Character soch raha hai... 🤔'), 2000)
    const t2 = setTimeout(() => setProcessingMsg('Answer bana raha hai... ✍️'), 4000)
    try {
      const data = await askQuestion(video.video_id, currentTime, questionText)
      clearTimeout(t1); clearTimeout(t2)
      setProcessing(false)
      setResponse(data)              // ← text shows instantly
      fireBackgroundTTS(data)        // ← audio fires in parallel, no await
      // Fetch character image in background (non-blocking)
      getCharacterImage(video.video_id, data.character).then(url => {
        if (url) setCharImageUrl(url)
      })
    } catch (e) {
      clearTimeout(t1); clearTimeout(t2)
      setError(e.message)
      setProcessing(false)
    }
  }

  const handleVoiceRecording = async (blob) => {
    if (ttsAbortRef.current) { ttsAbortRef.current.abort(); ttsAbortRef.current = null }
    setProcessing(true)
    setProcessingMsg('Aawaz sun raha hai... 👂')
    setError(null)
    setResponse(null)
    setCharImageUrl(null)
    setAudioLoading(false)
    const t1 = setTimeout(() => setProcessingMsg('Samajh raha hai... 🤔'), 2000)
    const t2 = setTimeout(() => setProcessingMsg('Answer bana raha hai... ✍️'), 4500)
    try {
      const data = await askVoice(video.video_id, currentTime, blob)
      clearTimeout(t1); clearTimeout(t2)
      setProcessing(false)
      setResponse(data)              // ← text shows instantly (~5s)
      fireBackgroundTTS(data)        // ← voice cloning starts in bg (~25-40s)
      // Fetch character image in background (non-blocking)
      getCharacterImage(video.video_id, data.character).then(url => {
        if (url) setCharImageUrl(url)
      })
    } catch (e) {
      clearTimeout(t1); clearTimeout(t2)
      setError(e.message)
      setProcessing(false)
    }
  }

  const formatTime = (s) => {
    const m = Math.floor(s / 60)
    const sec = Math.floor(s % 60)
    return `${m}:${sec.toString().padStart(2, '0')}`
  }

  return (
    <div className="card" style={{ overflow: 'hidden' }}>

      {/* ── Video area ── */}
      <div
        className="player-wrapper"
        onMouseMove={revealControls}
        style={{ cursor: showControls ? 'default' : 'none' }}
      >
        {streamUrl ? (
          <video
            ref={videoRef}
            src={streamUrl}
            preload="auto"
            style={{ width: '100%', height: '100%', objectFit: 'contain', background: '#000' }}
            onPlay={() => setPaused(false)}
            onPause={() => setPaused(true)}
            onClick={() => {
              if (videoRef.current?.paused) videoRef.current.play()
              else videoRef.current?.pause()
            }}
          />
        ) : (
          <div style={{
            width: '100%', height: '100%', display: 'flex', alignItems: 'center',
            justifyContent: 'center', background: '#111', color: 'var(--text-secondary)',
            flexDirection: 'column', gap: '1rem',
          }}>
            <span style={{ fontSize: '3rem' }}>📺</span>
            <p>Stream URL not available</p>
          </div>
        )}

        {/* Character popup — Naruto-style card with text + audio controls */}
        <CharacterPopup
          character={response?.character}
          text={response?.answer_text}
          audioRef={audioRef}
          audioLoading={audioLoading}
          visible={!!(response && !processing)}
          imageUrl={charImageUrl}
        />

        {/* Thinking spinner overlay */}
        {paused && asking && processing && (
          <div style={{
            position: 'absolute', inset: 0,
            background: 'rgba(0,0,0,0.4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            pointerEvents: 'none',
          }}>
            <div style={{ textAlign: 'center' }}>
              <div className="loading-ring" style={{ width: 60, height: 60, borderWidth: 6, margin: '0 auto 0.75rem' }} />
              <div style={{ color: 'white', fontSize: '0.9rem', fontWeight: 600, textShadow: '0 1px 4px #000' }}>
                {processingMsg}
              </div>
            </div>
          </div>
        )}

        {/* Video controls */}
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0,
          background: 'linear-gradient(transparent, rgba(0,0,0,0.8))',
          padding: '1.5rem 1rem 0.75rem',
          transition: 'opacity 0.3s',
          opacity: showControls || paused ? 1 : 0,
        }}>
          <input
            type="range" min={0} max={duration || 1} value={currentTime} step={0.5}
            onChange={(e) => {
              const t = parseFloat(e.target.value)
              setCurrentTime(t)
              if (videoRef.current) videoRef.current.currentTime = t
            }}
            style={{ width: '100%', accentColor: 'var(--primary)', marginBottom: '0.4rem' }}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.85rem' }}>
            <button
              className="btn btn-secondary"
              style={{ padding: '0.3rem 0.75rem', fontSize: '1rem' }}
              onClick={() => {
                if (videoRef.current?.paused) videoRef.current.play()
                else videoRef.current?.pause()
              }}
            >
              {paused ? '▶️' : '⏸️'}
            </button>
            <span style={{ color: 'rgba(255,255,255,0.7)' }}>
              {formatTime(currentTime)} / {formatTime(duration)}
            </span>
          </div>
        </div>
      </div>

      {/* ── Q&A Panel ── */}
      <div className="qa-panel">

        {/* Sandbox status pill */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.5rem' }}>
          <span style={{
            fontSize: '0.7rem', padding: '0.2rem 0.6rem', borderRadius: 20,
            background: sandboxReady ? 'rgba(0,200,100,0.15)' : 'rgba(255,180,0,0.15)',
            color: sandboxReady ? '#4ade80' : '#fbbf24',
            border: `1px solid ${sandboxReady ? 'rgba(74,222,128,0.3)' : 'rgba(251,191,36,0.3)'}`,
          }}>
            {sandboxReady ? '⚡ Voice AI Ready' : '🔥 Voice AI Warming up...'}
          </span>
        </div>

        {/* Initial CTA */}
        {!asking && !response && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
            <button className="btn btn-primary" onClick={handleAskClick} style={{ flex: '0 0 auto' }}>
              🎙️ Character se Puchho
            </button>
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Video pause karke apne favourite character se koi bhi sawaal puchho!
            </span>
          </div>
        )}

        {asking && (
          <div className="fade-in">

            {/* Input UI — hidden while processing */}
            {!processing && !response && (
              <>
                <p style={{ marginBottom: '0.75rem', fontWeight: 700, fontFamily: 'var(--font-display)' }}>
                  🎬 Video paused at {formatTime(currentTime)} — Kya poochhna hai?
                </p>

                <div className="qa-controls">
                  <MicButton onRecordingComplete={handleVoiceRecording} disabled={processing} />
                  <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>ya</div>
                  <div className="text-input-row" style={{ flex: 1 }}>
                    <input
                      className="text-input"
                      placeholder="Hindi ya English mein likhke puchho..."
                      value={textQuestion}
                      onChange={(e) => setTextQuestion(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && submitQuestion(textQuestion)}
                    />
                    <button className="btn btn-primary"
                      onClick={() => submitQuestion(textQuestion)}
                      disabled={!textQuestion.trim()}>
                      Send
                    </button>
                  </div>
                </div>

                <button className="btn btn-secondary" style={{ marginTop: '0.75rem', fontSize: '0.85rem' }}
                  onClick={handleContinue}>
                  ▶ Continue watching
                </button>
              </>
            )}

            {/* Processing spinner */}
            {processing && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', padding: '0.5rem 0' }}>
                <div className="loading-ring" />
                <div>
                  <div style={{ fontWeight: 700 }}>{processingMsg}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                    Scene context + character answer generating...
                  </div>
                </div>
              </div>
            )}

            {/* Error */}
            {error && (
              <div style={{
                background: 'rgba(255,50,50,0.15)', border: '1px solid rgba(255,50,50,0.3)',
                borderRadius: 10, padding: '0.75rem', color: '#ff6b6b', fontSize: '0.9rem',
              }}>
                ❌ {error}
              </div>
            )}

            {/* Response card — text shows instantly, audio loads in bg */}
            {response && !processing && (
              <div className="response-card">
                <div className="response-header">
                  <span className="char-avatar">
                    {CHAR_EMOJIS[response.character] || '🎭'}
                  </span>
                  <div>
                    <div style={{ fontWeight: 800, fontFamily: 'var(--font-display)' }}>
                      {response.character_display || response.character} bol raha hai:
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                      {response.audio_url
                        ? autoplayBlocked ? '🔇 Browser ne roka — neeche play karo' : '🔊 Awaaz aa rahi hai...'
                        : audioLoading
                          ? '⏳ Awaaz ban rahi hai...'
                          : '💬 Text answer'}
                    </div>
                  </div>
                </div>

                <div className="response-text">"{response.answer_text}"</div>

                {/* Audio player — manual controls only; auto-play handled by hidden audioRef */}
                {response.audio_url && autoplayBlocked && (
                  <audio
                    controls
                    src={response.audio_url}
                    style={{ width: '100%', marginTop: '0.5rem', height: 36 }}
                  />
                )}

                {/* Audio loading bar */}
                {audioLoading && !response.audio_url && (
                  <div style={{ marginTop: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <div className="loading-ring" style={{ width: 14, height: 14, borderWidth: 2 }} />
                    <span style={{ fontSize: '0.75rem', color: '#fbbf24' }}>
                      Awaaz ban rahi hai...
                    </span>
                  </div>
                )}

                <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.75rem', flexWrap: 'wrap' }}>
                  {response.audio_url && (
                    <button className="btn btn-secondary" style={{ fontSize: '0.85rem' }}
                      onClick={() => {
                        const el = audioRef.current
                        if (!el) return
                        el.pause()
                        el.currentTime = 0
                        el.play().catch(() => {})
                      }}>
                      🔊 Phir Suno
                    </button>
                  )}
                  <button className="btn btn-secondary" style={{ fontSize: '0.85rem' }}
                    onClick={() => { if (ttsAbortRef.current) { ttsAbortRef.current.abort(); ttsAbortRef.current = null } setResponse(null); setTextQuestion(''); setAudioLoading(false) }}>
                    🔄 Aur puchho
                  </button>
                  <button className="btn btn-primary" style={{ fontSize: '0.85rem' }}
                    onClick={handleContinue}>
                    ▶ Video continue karo
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Hidden audio player */}
      <audio ref={audioRef} style={{ display: 'none' }} />
    </div>
  )
}
