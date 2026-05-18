const STEPS = {
  started: { icon: '🚀', label: 'Starting...' },
  scene_indexing: { icon: '🎬', label: 'Analysing scenes with AI Vision...' },
  word_indexing: { icon: '🗣️', label: 'Transcribing dialogue...' },
  voice_cloning: { icon: '🎤', label: 'Cloning character voices...' },
  complete: { icon: '✅', label: 'Ready!' },
  error: { icon: '❌', label: 'Something went wrong' },
}

export default function ProcessingState({ status }) {
  if (!status) return null
  const { event, message, progress = 0, character } = status
  const step = STEPS[event] || STEPS.started

  return (
    <div className="card" style={{ padding: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
        <span style={{ fontSize: '2rem' }}>{step.icon}</span>
        <div>
          <div style={{ fontWeight: 700, fontFamily: 'var(--font-display)' }}>
            {message || step.label}
          </div>
          {character && (
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
              Character: {character}
            </div>
          )}
        </div>
        {event !== 'complete' && event !== 'error' && (
          <div className="loading-ring" style={{ marginLeft: 'auto' }} />
        )}
      </div>

      <div className="progress-bar">
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '0.4rem',
        fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
        <span>{progress}%</span>
        <span>{event === 'complete' ? 'Done!' : 'Processing...'}</span>
      </div>

      {/* Step indicators */}
      <div style={{ marginTop: '1.2rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
        {Object.entries(STEPS).filter(([k]) => k !== 'error').map(([key, s]) => {
          const stepOrder = ['started','scene_indexing','word_indexing','voice_cloning','complete']
          const currentIdx = stepOrder.indexOf(event)
          const thisIdx = stepOrder.indexOf(key)
          const isDone = thisIdx < currentIdx
          const isActive = key === event
          return (
            <div key={key} className={`processing-step ${isActive ? 'active' : ''} ${isDone ? 'done' : ''}`}>
              <span className="step-icon">{isDone ? '✓' : s.icon}</span>
              <span style={{ fontSize: '0.85rem' }}>{s.label}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
