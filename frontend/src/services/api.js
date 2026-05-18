const BASE = '/api'

export async function uploadVideo(file, title = '') {
  const form = new FormData()
  form.append('file', file)
  if (title) form.append('title', title)
  const res = await fetch(`${BASE}/upload`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function uploadFromUrl(url, title = '') {
  const res = await fetch(`${BASE}/upload-url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, title }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function processVideo(videoId, characters) {
  const res = await fetch(`${BASE}/process/${videoId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ characters }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export function subscribeToStatus(jobId, onEvent, onComplete, onError) {
  const es = new EventSource(`${BASE}/status/${jobId}`)
  es.onmessage = (e) => {
    const data = JSON.parse(e.data)
    onEvent(data)
    if (data.event === 'complete') { es.close(); onComplete(data) }
    if (data.event === 'error') { es.close(); onError(new Error(data.message)) }
  }
  es.onerror = () => { es.close(); onError(new Error('Connection lost')) }
  return () => es.close()
}

export async function listVideos() {
  const res = await fetch(`${BASE}/videos`)
  if (!res.ok) throw new Error(await res.text())
  return res.json().then(d => d.videos ?? d)
}

export async function getVideo(videoId) {
  const res = await fetch(`${BASE}/video/${videoId}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function askQuestion(videoId, timestamp, question) {
  const res = await fetch(`${BASE}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_id: videoId, timestamp, question }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function generateTTS(videoId, characterName, text, externalSignal = null) {
  // Voxtral — typically ~2s; 30s timeout is generous
  const controller = new AbortController()
  const timeoutId  = setTimeout(() => controller.abort(), 30 * 1000)
  // Forward external cancellation (e.g. new question asked)
  if (externalSignal) {
    if (externalSignal.aborted) { clearTimeout(timeoutId); throw new DOMException('Aborted', 'AbortError') }
    externalSignal.addEventListener('abort', () => controller.abort(), { once: true })
  }
  try {
    const res = await fetch(`${BASE}/generate-tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_id: videoId, character_name: characterName, text }),
      signal: controller.signal,
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  } finally {
    clearTimeout(timeoutId)
  }
}

export async function cloneVoice(videoId, characterName, text) {
  // OmniVoice clone — 8-word answer should complete in ~25-40s; 2-min timeout
  const controller = new AbortController()
  const timeoutId  = setTimeout(() => controller.abort(), 2 * 60 * 1000)
  try {
    const res = await fetch(`${BASE}/clone-voice`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_id: videoId, character_name: characterName, text }),
      signal: controller.signal,
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  } finally {
    clearTimeout(timeoutId)
  }
}

export async function askVoice(videoId, timestamp, audioBlob) {
  // Transcription + answer generation — 5-min timeout
  const controller = new AbortController()
  const timeoutId  = setTimeout(() => controller.abort(), 5 * 60 * 1000)
  try {
    const form = new FormData()
    form.append('video_id', videoId)
    form.append('timestamp', String(timestamp))
    form.append('audio', audioBlob, 'question.webm')
    const res = await fetch(`${BASE}/ask-voice`, {
      method: 'POST',
      body: form,
      signal: controller.signal,
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  } finally {
    clearTimeout(timeoutId)
  }
}

export async function getCharacters() {
  const res = await fetch(`${BASE}/characters`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function stopSandbox() {
  try {
    const res = await fetch(`${BASE}/stop-sandbox`, { method: 'POST' })
    return res.json()
  } catch { return null }
}

export async function warmupSandbox() {
  try {
    const res = await fetch(`${BASE}/warmup`, { method: 'POST' })
    return res.json()
  } catch { return null }
}

export async function getSandboxStatus() {
  try {
    const res = await fetch(`${BASE}/sandbox-status`)
    return res.json()
  } catch { return { ready: false, status: 'unknown' } }
}

export async function getCharacterImage(videoId, characterName) {
  try {
    const res = await fetch(`${BASE}/character-image/${videoId}/${encodeURIComponent(characterName)}`)
    if (!res.ok) return null
    const data = await res.json()
    return data.image_url || null
  } catch { return null }
}
