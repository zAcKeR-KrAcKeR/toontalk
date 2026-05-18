import { useEffect, useRef, useState } from 'react'

// Remove white/near-white background from an img element using canvas
function removeWhiteBg(imgEl, tolerance = 30) {
  try {
    const canvas = document.createElement('canvas')
    canvas.width  = imgEl.naturalWidth
    canvas.height = imgEl.naturalHeight
    const ctx = canvas.getContext('2d')
    ctx.drawImage(imgEl, 0, 0)
    const id   = ctx.getImageData(0, 0, canvas.width, canvas.height)
    const data = id.data
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i], g = data[i + 1], b = data[i + 2]
      if (r >= 255 - tolerance && g >= 255 - tolerance && b >= 255 - tolerance) {
        // Soft edge: alpha proportional to how close to pure white
        const whiteness = Math.min(r, g, b) / 255
        data[i + 3] = Math.round((1 - whiteness) * 255 * 2)
      }
    }
    ctx.putImageData(id, 0, 0)
    imgEl.src = canvas.toDataURL('image/png')
  } catch (e) {
    // CORS or other error — leave image as-is
  }
}

const CHAR_IMAGES = {
  shinchan: '/characters/shinchan.webp',
  misae:    '/characters/misae.png',
  hiroshi:  '/characters/hiroshi_hd.webp',
}


const CHAR_THEME = {
  shinchan: {
    topBg:      '#C8E600',
    topBg2:     '#F5FF00',
    botBg:      '#FF6B00',
    botBg2:     '#CC2200',
    lightning:  '#FFE000',
    nameColor:  '#FF4500',
    tornColor:  '#fff',
    exclaim:    'YA-HOO!!',
    particles:  ['⭐','✨','🌟','💥','⚡'],
    auraColor:  '#FFD600',
    auraColor2: '#FF6B00',
    sfx:        'ACTION!!',
  },
  misae: {
    topBg:      '#FF6EC7',
    topBg2:     '#FFB3E6',
    botBg:      '#C2185B',
    botBg2:     '#7B0040',
    lightning:  '#FF80AB',
    nameColor:  '#FFB3E6',
    tornColor:  '#fff',
    exclaim:    'SHINCHAAAN!!',
    particles:  ['🌸','💮','🌺','💖','✨'],
    auraColor:  '#FF6EC7',
    auraColor2: '#FF1493',
    sfx:        'OKAASAN!!',
  },
  hiroshi: {
    topBg:      '#29B6F6',
    topBg2:     '#81D4FA',
    botBg:      '#01579B',
    botBg2:     '#003060',
    lightning:  '#E1F5FE',
    nameColor:  '#B3E5FC',
    tornColor:  '#fff',
    exclaim:    'YARE YARE...',
    particles:  ['💼','💤','🍺','⭐','✨'],
    auraColor:  '#29B6F6',
    auraColor2: '#0288D1',
    sfx:        'SIGH...',
  },
  generic: {
    topBg:      '#A78BFA',
    topBg2:     '#DDD6FE',
    botBg:      '#5B21B6',
    botBg2:     '#2E1065',
    lightning:  '#E9D5FF',
    nameColor:  '#DDD6FE',
    tornColor:  '#fff',
    exclaim:    'SUGOI!!',
    particles:  ['✨','⭐','💫','🌟','💥'],
    auraColor:  '#A78BFA',
    auraColor2: '#7C3AED',
    sfx:        'DESU!!',
  },
}

// Torn paper SVG paths
const makeTorn = (w = 1200, seed = 1) => {
  const pts = [], pts2 = []
  const segs = 70
  const step = w / segs
  pts.push('M0,0')
  pts2.push(`M0,5`)
  for (let i = 0; i <= segs; i++) {
    const x = i * step
    const t = i * seed * 0.9
    const y  = i % 2 === 0 ? Math.abs(Math.sin(t) * 4) : 12 + Math.cos(t * 1.7) * 5
    const y2 = y + 4 + Math.sin(i * 0.6) * 2
    pts.push(`L${x.toFixed(1)},${y.toFixed(1)}`)
    pts2.push(`L${x.toFixed(1)},${y2.toFixed(1)}`)
  }
  pts.push(`L${w},0 Z`)
  pts2.push(`L${w},5`)
  for (let i = segs; i >= 0; i--) {
    const x = i * step
    const t = i * seed * 0.9
    const y2 = (i % 2 === 0 ? Math.abs(Math.sin(t) * 4) : 12 + Math.cos(t * 1.7) * 5) + 4 + Math.sin(i * 0.6) * 2
    pts2.push(`L${x.toFixed(1)},${y2.toFixed(1)}`)
  }
  pts2.push('Z')
  return { clip: pts.join(' '), edge: pts2.join(' ') }
}

const TORN = makeTorn(1200, 1.2)
const BANNER_H = 165
const TEAR_Y   = 74
const CHAR_H   = 220

export default function CharacterPopup({ character, text, audioRef, visible, audioLoading, imageUrl }) {
  const [phase,       setPhase]       = useState('hidden')
  const [isPlaying,   setIsPlaying]   = useState(false)
  const [charIdx,     setCharIdx]     = useState(0)
  const [lightning,   setLightning]   = useState([])
  const [particles,   setParticles]   = useState([])
  const [showImpact,  setShowImpact]  = useState(false)
  const [showSFX,     setShowSFX]     = useState(false)
  const [auraRings,   setAuraRings]   = useState([])
  const [speedLines,  setSpeedLines]  = useState([])
  const [glitch,      setGlitch]      = useState(false)
  const [replayFlash, setReplayFlash] = useState(false)
  const typeTimer  = useRef(null)
  const lightTimer = useRef(null)
  const partTimer  = useRef(null)
  const ringTimer  = useRef(null)

  const theme = CHAR_THEME[character] || CHAR_THEME.generic
  const img   = imageUrl || CHAR_IMAGES[character] || null

  // ── Phase ────────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (visible) {
      setPhase('in')
      setCharIdx(0)
      // Impact flash on entry
      setShowImpact(true)
      setTimeout(() => setShowImpact(false), 180)
      // SFX word
      setTimeout(() => { setShowSFX(true); setTimeout(() => setShowSFX(false), 900) }, 350)
      // Speed lines on entry
      const lines = Array.from({ length: 18 }, (_, i) => ({
        id: i, angle: i * (360 / 18),
        len: 60 + Math.random() * 80,
        opacity: 0.4 + Math.random() * 0.4,
      }))
      setSpeedLines(lines)
      setTimeout(() => setSpeedLines([]), 500)
      // Aura rings burst
      const rings = [0, 120, 250].map(delay => ({ id: delay, delay }))
      setAuraRings(rings)
      setTimeout(() => setAuraRings([]), 1200)
    } else {
      setPhase('out')
      setShowSFX(false)
      setSpeedLines([])
      const t = setTimeout(() => {
        setPhase('hidden')
        setLightning([])
        setParticles([])
      }, 460)
      return () => clearTimeout(t)
    }
  }, [visible])

  // ── Typewriter ────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!visible || !text) return
    setCharIdx(0)
    clearInterval(typeTimer.current)
    let i = 0
    typeTimer.current = setInterval(() => {
      i++; setCharIdx(i)
      if (i >= text.length) clearInterval(typeTimer.current)
      // random glitch during typing
      if (Math.random() < 0.08) {
        setGlitch(true); setTimeout(() => setGlitch(false), 80)
      }
    }, 28)
    return () => clearInterval(typeTimer.current)
  }, [text, visible])

  // ── Lightning bolts ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (!visible) return
    lightTimer.current = setInterval(() => {
      setLightning(Array.from({ length: 4 }, () => ({
        id: Math.random(),
        top: 15 + Math.random() * 65,
        left: 2 + Math.random() * 52,
        width: 30 + Math.random() * 120,
        angle: -12 + Math.random() * 24,
        opacity: 0.45 + Math.random() * 0.55,
        thick: 1 + Math.random() * 2,
      })))
      setTimeout(() => setLightning([]), 100)
    }, 600 + Math.random() * 500)
    return () => clearInterval(lightTimer.current)
  }, [visible])

  // ── Floating particles ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!visible) return
    partTimer.current = setInterval(() => {
      const emoji = theme.particles[Math.floor(Math.random() * theme.particles.length)]
      const p = {
        id: Math.random(), emoji,
        x: 5 + Math.random() * 85,
        startY: 90 + Math.random() * 20,
        size: 12 + Math.random() * 14,
        duration: 1.2 + Math.random() * 1.2,
        drift: -15 + Math.random() * 30,
      }
      setParticles(prev => [...prev.slice(-8), p])
    }, 400)
    return () => clearInterval(partTimer.current)
  }, [visible, theme])

  // ── Audio tracking ────────────────────────────────────────────────────────────
  useEffect(() => {
    const el = audioRef?.current
    if (!el) return
    const on  = () => setIsPlaying(true)
    const off = () => setIsPlaying(false)
    el.addEventListener('play',  on)
    el.addEventListener('pause', off)
    el.addEventListener('ended', off)
    return () => {
      el.removeEventListener('play',  on)
      el.removeEventListener('pause', off)
      el.removeEventListener('ended', off)
    }
  }, [audioRef])

  const handleReplay = () => {
    const el = audioRef?.current
    if (el) { el.currentTime = 0; el.play().catch(() => {}) }
    setReplayFlash(true); setTimeout(() => setReplayFlash(false), 300)
    setCharIdx(0)
    clearInterval(typeTimer.current)
    let i = 0
    typeTimer.current = setInterval(() => {
      i++; setCharIdx(i)
      if (i >= (text?.length || 0)) clearInterval(typeTimer.current)
    }, 28)
  }

  if (phase === 'hidden') return null
  const displayText = text ? text.slice(0, charIdx) : ''

  return (
    <>
      <style>{`
        @keyframes bannerIn {
          0%   { transform: translateY(100%) skewY(2deg); filter: brightness(2); }
          50%  { transform: translateY(-10px) skewY(-0.5deg); filter: brightness(1.3); }
          70%  { transform: translateY(6px) skewY(0.3deg); filter: brightness(1); }
          85%  { transform: translateY(-3px); }
          100% { transform: translateY(0px) skewY(0deg); filter: brightness(1); }
        }
        @keyframes bannerOut {
          0%   { transform: translateY(0px) scaleY(1); opacity: 1; }
          30%  { transform: translateY(-8px) scaleY(1.04); }
          100% { transform: translateY(115%) scaleY(0.6); opacity: 0; }
        }
        @keyframes charIn {
          0%   { transform: translateY(100px) scale(0.4) rotate(15deg); opacity: 0; filter: brightness(3); }
          55%  { transform: translateY(-18px) scale(1.1) rotate(-4deg); opacity: 1; filter: brightness(1.4); }
          75%  { transform: translateY(8px) scale(0.95) rotate(1.5deg); filter: brightness(1); }
          90%  { transform: translateY(-4px) scale(1.02); }
          100% { transform: translateY(0px) scale(1) rotate(0deg); filter: brightness(1); }
        }
        @keyframes charIdle {
          0%,100% { transform: translateY(0px) rotate(0deg); }
          30%      { transform: translateY(-9px) rotate(-2deg); }
          65%      { transform: translateY(-5px) rotate(1.5deg); }
        }
        @keyframes charTalk {
          0%,100% { transform: scaleY(1) scaleX(1) rotate(0deg); }
          25%      { transform: scaleY(1.05) scaleX(0.96) rotate(-1deg); }
          75%      { transform: scaleY(0.95) scaleX(1.04) rotate(1deg); }
        }
        @keyframes impactFlash {
          0%   { opacity: 0.85; }
          100% { opacity: 0; }
        }
        @keyframes sfxPop {
          0%   { transform: translate(-50%,-50%) scale(0.2) rotate(-15deg); opacity: 0; }
          40%  { transform: translate(-50%,-50%) scale(1.2) rotate(5deg); opacity: 1; }
          70%  { transform: translate(-50%,-50%) scale(0.95) rotate(-2deg); opacity: 1; }
          100% { transform: translate(-50%,-50%) scale(1.1) rotate(0deg); opacity: 0; }
        }
        @keyframes auraRing {
          0%   { transform: translate(-50%,-50%) scale(0.3); opacity: 0.9; }
          100% { transform: translate(-50%,-50%) scale(3.5); opacity: 0; }
        }
        @keyframes speedLine {
          0%   { opacity: 0.7; transform-origin: center; }
          100% { opacity: 0; }
        }
        @keyframes floatParticle {
          0%   { transform: translateY(0px) translateX(0px) rotate(0deg); opacity: 1; }
          100% { transform: translateY(-90px) translateX(var(--drift)) rotate(360deg); opacity: 0; }
        }
        @keyframes wavePulse {
          0%,100% { transform: scaleY(0.25); opacity: 0.5; }
          50%      { transform: scaleY(1);    opacity: 1; }
        }
        @keyframes cursor {
          0%,100% { opacity: 1; } 50% { opacity: 0; }
        }
        @keyframes shimmer {
          0%   { transform: translateX(-120%) skewX(-15deg); }
          100% { transform: translateX(220%) skewX(-15deg); }
        }
        @keyframes nameStamp {
          0%   { transform: scale(2.5) rotate(-8deg); opacity: 0; filter: blur(4px); }
          60%  { transform: scale(0.92) rotate(1deg); opacity: 1; filter: blur(0); }
          80%  { transform: scale(1.04) rotate(-0.5deg); }
          100% { transform: scale(1) rotate(0deg); opacity: 1; }
        }
        @keyframes topStripe {
          0%   { background-position: 0% 50%; }
          100% { background-position: 100% 50%; }
        }
        @keyframes halftone {
          0%,100% { opacity: 0.07; } 50% { opacity: 0.13; }
        }
        @keyframes replayBurst {
          0%   { box-shadow: 0 0 0 0 ${CHAR_THEME[character || 'generic']?.topBg}cc; transform: scale(1); }
          50%  { box-shadow: 0 0 0 12px transparent; transform: scale(1.1); }
          100% { box-shadow: 0 0 0 0 transparent; transform: scale(1); }
        }
        @keyframes glitchLeft {
          0%,100% { clip-path: none; transform: none; }
          20%      { clip-path: polygon(0 15%,100% 15%,100% 30%,0 30%); transform: translateX(-3px); }
          40%      { clip-path: polygon(0 60%,100% 60%,100% 75%,0 75%); transform: translateX(3px); }
          60%      { clip-path: polygon(0 40%,100% 40%,100% 55%,0 55%); transform: translateX(-2px); }
        }
        @keyframes fireRise {
          0%,100% { transform: scaleY(1) skewX(0deg); opacity: 0.8; }
          40%      { transform: scaleY(1.15) skewX(-5deg); opacity: 1; }
          70%      { transform: scaleY(0.85) skewX(5deg); opacity: 0.6; }
        }
        @keyframes diagonalMove {
          0%   { transform: translateX(-100%); }
          100% { transform: translateX(200%); }
        }
      `}</style>

      {/* ── IMPACT FLASH — full video white flash on entry ── */}
      {showImpact && (
        <div style={{
          position: 'absolute', inset: 0, zIndex: 100,
          background: 'rgba(255,255,255,0.65)',
          animation: 'impactFlash 0.18s ease-out forwards',
          pointerEvents: 'none',
        }} />
      )}

      {/* ── SPEED LINES — radial burst from character side ── */}
      {speedLines.length > 0 && (
        <div style={{
          position: 'absolute', inset: 0, zIndex: 38, pointerEvents: 'none',
          overflow: 'hidden',
        }}>
          {speedLines.map(l => (
            <div key={l.id} style={{
              position: 'absolute',
              right: 80, bottom: BANNER_H / 2 + 20,
              width: l.len,
              height: 2,
              background: `linear-gradient(90deg, transparent, ${theme.auraColor}88)`,
              transformOrigin: 'right center',
              transform: `rotate(${l.angle}deg)`,
              opacity: l.opacity,
              animation: 'speedLine 0.5s ease-out forwards',
            }} />
          ))}
        </div>
      )}

      {/* ── AURA RINGS — expand from character on entry ── */}
      {auraRings.map(r => (
        <div key={r.id} style={{
          position: 'absolute',
          right: 80, bottom: BANNER_H * 0.6,
          width: 80, height: 80,
          border: `3px solid ${theme.auraColor}`,
          borderRadius: '50%',
          zIndex: 38,
          pointerEvents: 'none',
          animation: `auraRing 0.9s ease-out ${r.delay}ms forwards`,
        }} />
      ))}

      {/* ── SFX WORD (YAHOO! / OKAASAN! etc) ── */}
      {showSFX && (
        <div style={{
          position: 'absolute',
          right: 110, bottom: BANNER_H + 30,
          zIndex: 60, pointerEvents: 'none',
          fontFamily: "'Arial Black','Impact',sans-serif",
          fontWeight: 900,
          fontSize: '1.6rem',
          letterSpacing: '0.05em',
          color: theme.topBg,
          textShadow: `3px 3px 0 #000, -1px -1px 0 #000, 0 0 20px ${theme.auraColor}`,
          transform: 'translate(-50%,-50%)',
          animation: 'sfxPop 0.9s cubic-bezier(0.34,1.56,0.64,1) forwards',
          whiteSpace: 'nowrap',
        }}>
          {theme.sfx}
        </div>
      )}

      {/* ── FLOATING PARTICLES ── */}
      {particles.map(p => (
        <div key={p.id} style={{
          position: 'absolute',
          left: `${p.x}%`,
          bottom: `${p.startY}%`,
          fontSize: p.size,
          zIndex: 39,
          pointerEvents: 'none',
          '--drift': `${p.drift}px`,
          animation: `floatParticle ${p.duration}s ease-out forwards`,
        }}>
          {p.emoji}
        </div>
      ))}

      {/* ══════════════════════════════════════════════════════════════════════
          MAIN BANNER
      ══════════════════════════════════════════════════════════════════════ */}
      <div style={{
        position: 'absolute',
        bottom: 0, left: 0, right: 0,
        height: BANNER_H,
        zIndex: 40,
        animation: phase === 'in'
          ? 'bannerIn 0.68s cubic-bezier(0.22,1,0.36,1) forwards'
          : 'bannerOut 0.46s ease-in forwards',
        pointerEvents: 'none',
      }}>

        {/* ── TOP HALF ──────────────────────────────────────────────────────── */}
        <div style={{
          position: 'absolute',
          top: 0, left: 0, right: 0,
          height: TEAR_Y,
          overflow: 'hidden',
          background: `linear-gradient(105deg, ${theme.topBg} 0%, ${theme.topBg2} 45%, ${theme.topBg} 100%)`,
          backgroundSize: '200% 100%',
          animation: 'topStripe 3s linear infinite',
        }}>
          {/* Diagonal stripe texture */}
          <div style={{
            position: 'absolute', inset: 0,
            background: `repeating-linear-gradient(
              -45deg,
              transparent 0px, transparent 8px,
              rgba(255,255,255,0.08) 8px, rgba(255,255,255,0.08) 10px
            )`,
          }} />
          {/* Halftone dots */}
          <div style={{
            position: 'absolute', inset: 0,
            backgroundImage: `radial-gradient(circle, rgba(0,0,0,0.18) 1px, transparent 1px)`,
            backgroundSize: '8px 8px',
            animation: 'halftone 2s ease-in-out infinite',
          }} />
          {/* Shimmer */}
          <div style={{
            position: 'absolute', inset: 0,
            background: 'linear-gradient(105deg, transparent 30%, rgba(255,255,255,0.35) 50%, transparent 70%)',
            animation: 'shimmer 2.2s ease-in-out infinite',
            pointerEvents: 'none',
          }} />
          {/* Character name — stamps in */}
          <div style={{
            position: 'absolute',
            left: 18, top: '50%',
            transform: 'translateY(-50%)',
            fontFamily: "'Arial Black','Impact',sans-serif",
            fontWeight: 900,
            fontSize: '1.1rem',
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: theme.nameColor,
            textShadow: `3px 3px 0 #000, -1px -1px 0 rgba(0,0,0,0.5), 0 0 16px ${theme.botBg}`,
            whiteSpace: 'nowrap',
            animation: phase === 'in' ? 'nameStamp 0.55s cubic-bezier(0.34,1.56,0.64,1) 0.25s both' : 'none',
          }}>
            ★ {character?.toUpperCase()} KA JAWAB!
          </div>
          {/* Moving diagonal accent bar */}
          <div style={{
            position: 'absolute', inset: 0,
            background: `linear-gradient(105deg, transparent 20%, ${theme.botBg}22 50%, transparent 80%)`,
            animation: 'diagonalMove 1.8s ease-in-out infinite',
          }} />
        </div>

        {/* ── TORN PAPER SVG ────────────────────────────────────────────────── */}
        <svg viewBox="0 0 1200 22" preserveAspectRatio="none" style={{
          position: 'absolute', top: TEAR_Y - 3,
          left: 0, right: 0, width: '100%', height: 24,
          zIndex: 10, display: 'block',
        }}>
          {/* Drop shadow layer */}
          <path d={TORN.edge} fill="rgba(0,0,0,0.5)" transform="translate(0,5)" />
          {/* Inner shadow */}
          <path d={TORN.edge} fill="rgba(0,0,0,0.25)" transform="translate(0,2)" />
          {/* White paper edge */}
          <path d={TORN.edge} fill={theme.tornColor} />
          {/* Top accent line */}
          <path d={TORN.clip} fill={`${theme.topBg}55`} />
        </svg>

        {/* ── BOTTOM HALF ───────────────────────────────────────────────────── */}
        <div style={{
          position: 'absolute',
          top: TEAR_Y + 19, left: 0, right: 0, bottom: 0,
          overflow: 'hidden',
          background: `linear-gradient(135deg, ${theme.botBg} 0%, ${theme.botBg2} 100%)`,
        }}>
          {/* Fire glow blobs */}
          <div style={{
            position: 'absolute', left: -40, top: -30,
            width: 340, height: 160,
            background: `radial-gradient(ellipse, ${theme.botBg}bb 0%, transparent 60%)`,
            animation: 'fireRise 1.1s ease-in-out infinite',
            pointerEvents: 'none',
          }} />
          <div style={{
            position: 'absolute', right: 100, bottom: -20,
            width: 200, height: 120,
            background: `radial-gradient(ellipse, ${theme.auraColor}44 0%, transparent 65%)`,
            animation: 'fireRise 1.5s ease-in-out infinite 0.4s',
            pointerEvents: 'none',
          }} />
          {/* Scanlines */}
          <div style={{
            position: 'absolute', inset: 0,
            background: 'repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,0,0,0.07) 3px,rgba(0,0,0,0.07) 4px)',
            pointerEvents: 'none',
          }} />
          {/* Lightning bolts */}
          {lightning.map(b => (
            <div key={b.id} style={{
              position: 'absolute',
              top: `${b.top}%`, left: `${b.left}%`,
              width: b.width, height: b.thick,
              background: `linear-gradient(90deg, transparent, ${theme.lightning}cc, ${theme.lightning}, ${theme.lightning}cc, transparent)`,
              transform: `rotate(${b.angle}deg)`,
              opacity: b.opacity,
              borderRadius: 2,
              boxShadow: `0 0 6px 1px ${theme.lightning}88`,
              pointerEvents: 'none',
            }} />
          ))}

          {/* ── Text + controls ── */}
          <div style={{
            position: 'absolute', inset: 0,
            paddingRight: 148, paddingLeft: 18,
            display: 'flex', flexDirection: 'column',
            justifyContent: 'center', gap: 5,
            pointerEvents: 'auto',
          }}>
            {/* Dialogue */}
            <div style={{
              color: '#fff',
              fontSize: '0.92rem',
              fontWeight: 700,
              lineHeight: 1.4,
              textShadow: '0 1px 6px #000, 0 0 3px #000',
              fontFamily: "'Segoe UI',sans-serif",
              minHeight: 42,
              animation: glitch ? 'glitchLeft 0.08s steps(1) forwards' : 'none',
            }}>
              "{displayText}
              {charIdx < (text?.length || 0) && (
                <span style={{
                  display: 'inline-block', width: 2, height: '0.85em',
                  background: theme.lightning, marginLeft: 1,
                  verticalAlign: 'middle',
                  animation: 'cursor 0.5s steps(1) infinite',
                }} />
              )}"
            </div>

            {/* Controls row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2 }}>
              {audioLoading ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <div style={{
                    width: 10, height: 10, borderRadius: '50%',
                    border: `2px solid ${theme.lightning}`,
                    borderTopColor: 'transparent',
                    animation: 'topStripe 0.7s linear infinite',
                  }} />
                  <span style={{ fontSize: '0.68rem', color: theme.lightning, fontWeight: 600 }}>
                    awaaz aa rahi hai...
                  </span>
                </div>
              ) : (
                <button onClick={handleReplay} style={{
                  background: `linear-gradient(135deg, ${theme.topBg} 0%, ${theme.botBg} 100%)`,
                  border: `2px solid ${theme.topBg}`,
                  borderRadius: 4,
                  padding: '3px 14px',
                  color: '#000',
                  fontWeight: 900,
                  fontSize: '0.7rem',
                  cursor: 'pointer',
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  fontFamily: "'Arial Black',sans-serif",
                  animation: replayFlash ? 'replayBurst 0.3s ease-out forwards' : 'none',
                  boxShadow: `0 2px 10px ${theme.topBg}66, inset 0 1px 0 rgba(255,255,255,0.3)`,
                  transition: 'transform 0.1s',
                }}>
                  ▶ REPLAY
                </button>
              )}

              {/* Waveform */}
              {isPlaying && (
                <div style={{ display: 'flex', gap: 2, alignItems: 'flex-end', height: 20 }}>
                  {[4,8,16,12,20,14,9,18,11,6].map((h, i) => (
                    <div key={i} style={{
                      width: 3, height: h,
                      background: `linear-gradient(0deg, ${theme.botBg}, ${theme.lightning})`,
                      borderRadius: 2,
                      animation: `wavePulse ${0.22 + i * 0.055}s ease-in-out infinite`,
                      animationDelay: `${i * 0.03}s`,
                      boxShadow: `0 0 4px ${theme.lightning}66`,
                    }} />
                  ))}
                </div>
              )}

              {/* Replay counter dots */}
              {!isPlaying && !audioLoading && (
                <div style={{ display: 'flex', gap: 3, alignItems: 'center' }}>
                  {[0,1,2].map(i => (
                    <div key={i} style={{
                      width: 5, height: 5, borderRadius: '50%',
                      background: theme.lightning,
                      opacity: 0.4 + i * 0.2,
                      animation: `wavePulse ${0.8 + i * 0.2}s ease-in-out infinite`,
                      animationDelay: `${i * 0.15}s`,
                    }} />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── CHARACTER IMAGE — right, bursting above banner ────────────────── */}
        <div style={{
          position: 'absolute',
          right: 18, bottom: 0,
          width: 130, height: CHAR_H,
          zIndex: 20,
          animation: phase === 'in'
            ? 'charIn 0.75s cubic-bezier(0.34,1.56,0.64,1) 0.2s both'
            : 'none',
        }}>
          {/* Energy halo */}
          <div style={{
            position: 'absolute',
            top: '50%', left: '50%',
            width: 110, height: 110,
            marginLeft: -55, marginTop: -55,
            borderRadius: '50%',
            background: `radial-gradient(ellipse, ${theme.auraColor}44 0%, transparent 70%)`,
            animation: 'fireRise 1.3s ease-in-out infinite',
            filter: 'blur(8px)',
          }} />
          {/* Ground shadow */}
          <div style={{
            position: 'absolute', bottom: 2,
            left: '50%', transform: 'translateX(-50%)',
            width: 88, height: 14,
            background: `radial-gradient(ellipse, ${theme.auraColor2}99, transparent 70%)`,
            filter: 'blur(5px)',
            animation: 'fireRise 1s ease-in-out infinite',
          }} />
          {/* Character */}
          <div style={{
            width: '100%', height: '100%',
            animation: isPlaying
              ? 'charTalk 0.3s ease-in-out infinite'
              : 'charIdle 2.9s ease-in-out infinite',
            transformOrigin: 'bottom center',
          }}>
            {img ? (
              <img
                src={img}
                alt={character}
                crossOrigin="anonymous"
                onLoad={e => removeWhiteBg(e.target, 40)}
                style={{
                  width: '100%', height: '100%',
                  objectFit: 'contain',
                  objectPosition: 'bottom center',
                  display: 'block',
                  filter: `
                    drop-shadow(0 0 16px ${theme.auraColor}cc)
                    drop-shadow(0 0 6px ${theme.auraColor2}99)
                    drop-shadow(3px 6px 12px #000d)
                  `,
                }}
              />
            ) : (
              <img
                src="/characters/default-banner.svg"
                alt={character || 'character'}
                style={{
                  width: '100%', height: '100%',
                  objectFit: 'contain',
                  objectPosition: 'bottom center',
                  display: 'block',
                  filter: `drop-shadow(0 0 16px ${theme.auraColor}cc) drop-shadow(3px 6px 12px #000d)`,
                  opacity: 0.9,
                }}
              />
            )}
          </div>
        </div>

        {/* Bottom accent stripe */}
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0, height: 3,
          background: `linear-gradient(90deg, transparent, ${theme.topBg2}, ${theme.botBg}, ${theme.topBg}, transparent)`,
          animation: 'topStripe 2s linear infinite',
        }} />
      </div>
    </>
  )
}
