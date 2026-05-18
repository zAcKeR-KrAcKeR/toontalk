import { useRef, useState } from 'react'
import { AudioRecorder } from '../services/audioRecorder'

export default function MicButton({ onRecordingComplete, disabled }) {
  const [recording, setRecording] = useState(false)
  const recorderRef = useRef(null)

  const handleClick = async () => {
    if (recording) {
      // Stop
      setRecording(false)
      const blob = await recorderRef.current.stop()
      onRecordingComplete(blob)
    } else {
      // Start
      try {
        recorderRef.current = new AudioRecorder()
        await recorderRef.current.start()
        setRecording(true)
      } catch (e) {
        alert('Microphone permission denied. Please allow microphone access.')
      }
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem' }}>
      <button
        className={`mic-btn ${recording ? 'recording' : ''}`}
        onClick={handleClick}
        disabled={disabled}
        title={recording ? 'Stop recording' : 'Hold to ask a question'}
      >
        {recording ? '⏹️' : '🎙️'}
      </button>

      {recording && (
        <div className="waveform">
          {[1,2,3,4,5].map(i => (
            <div key={i} className="waveform-bar" style={{ animationDelay: `${i*0.1}s` }} />
          ))}
        </div>
      )}

      <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', textAlign: 'center' }}>
        {recording ? 'Tap to stop' : 'Tap to ask'}
      </span>
    </div>
  )
}
