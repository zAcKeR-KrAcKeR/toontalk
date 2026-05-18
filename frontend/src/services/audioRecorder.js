/**
 * Audio recorder using MediaRecorder API.
 * Returns a promise that resolves with the recorded Blob.
 */
export class AudioRecorder {
  constructor() {
    this.mediaRecorder = null
    this.chunks = []
    this.stream = null
  }

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    this.chunks = []
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : 'audio/webm'
    this.mediaRecorder = new MediaRecorder(this.stream, { mimeType })
    this.mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data)
    }
    this.mediaRecorder.start(100)
  }

  stop() {
    return new Promise((resolve) => {
      this.mediaRecorder.onstop = () => {
        const blob = new Blob(this.chunks, { type: 'audio/webm' })
        this.stream.getTracks().forEach((t) => t.stop())
        resolve(blob)
      }
      this.mediaRecorder.stop()
    })
  }

  get isRecording() {
    return this.mediaRecorder?.state === 'recording'
  }
}
