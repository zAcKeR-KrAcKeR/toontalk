import { useEffect, useRef, useState } from 'react'

const SHAPES = {
  round: (color, border) => `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 120" width="100%" height="100%">
      <ellipse cx="100" cy="55" rx="95" ry="50" fill="${color}" stroke="${border}" stroke-width="3"/>
      <polygon points="60,100 80,105 55,118" fill="${color}" stroke="${border}" stroke-width="3" stroke-linejoin="round"/>
    </svg>`,
  cloud: (color, border) => `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 130" width="100%" height="100%">
      <path d="M30,90 Q10,90 10,70 Q10,50 30,50 Q30,25 55,25 Q65,10 85,15 Q95,5 115,10 Q135,5 145,20 Q170,20 170,45 Q190,45 190,65 Q190,90 165,90 Z"
        fill="${color}" stroke="${border}" stroke-width="3"/>
      <polygon points="55,88 75,95 50,115" fill="${color}" stroke="${border}" stroke-width="3" stroke-linejoin="round"/>
    </svg>`,
  jagged: (color, border) => `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 130" width="100%" height="100%">
      <polygon points="
        10,40 25,10 40,30 60,5 80,25 100,0 120,22 140,5 160,28 180,8 210,35
        215,60 200,85 215,110 180,100 160,115 140,95 120,118 100,98 80,115 60,95 40,112 20,100 5,85 10,60"
        fill="${color}" stroke="${border}" stroke-width="3"/>
      <polygon points="70,100 95,108 65,125" fill="${color}" stroke="${border}" stroke-width="3" stroke-linejoin="round"/>
    </svg>`,
}

export default function MangaBubble({ text, characterName, style = {}, position = {} }) {
  const [visibleChars, setVisibleChars] = useState(0)
  const timerRef = useRef(null)

  const shape = style.shape || 'round'
  const bg = style.background || '#fff'
  const border = style.border || '#333'
  const textColor = style.text_color || '#333'
  const font = style.font || 'Nunito, sans-serif'

  // Typewriter animation
  useEffect(() => {
    setVisibleChars(0)
    if (!text) return
    let i = 0
    timerRef.current = setInterval(() => {
      i++
      setVisibleChars(i)
      if (i >= text.length) clearInterval(timerRef.current)
    }, 40)
    return () => clearInterval(timerRef.current)
  }, [text])

  // Compute position style
  const pos = {
    position: 'absolute',
    left: `${position.x_percent ?? 5}%`,
    top: `${position.y_percent ?? 5}%`,
    maxWidth: '45%',
    zIndex: 50,
  }

  const svgFn = SHAPES[shape] || SHAPES.round
  const svgMarkup = svgFn(bg, border)

  return (
    <div className={`manga-bubble bubble-${shape}`} style={pos}>
      {/* SVG background shape */}
      <div
        style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}
        dangerouslySetInnerHTML={{ __html: svgMarkup }}
      />
      {/* Text content */}
      <div style={{
        position: 'relative',
        padding: shape === 'jagged' ? '1.6rem 2rem' : '1rem 1.4rem',
        fontFamily: font,
        color: textColor,
        fontWeight: 700,
        fontSize: 'clamp(0.75rem, 1.5vw, 0.95rem)',
        lineHeight: 1.5,
        minWidth: 120,
        minHeight: 60,
      }}>
        <div style={{ fontSize: '0.65rem', fontWeight: 900, textTransform: 'uppercase',
          letterSpacing: '0.1em', opacity: 0.6, marginBottom: '0.2rem' }}>
          {characterName}
        </div>
        <div className="bubble-text">
          {text.slice(0, visibleChars)}
          {visibleChars < text.length && <span style={{ opacity: 0.4 }}>|</span>}
        </div>
      </div>
    </div>
  )
}
