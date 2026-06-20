class WakeWordProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const processorOptions = options?.processorOptions || {};
    this.targetSampleRate = Number(processorOptions.targetSampleRate || 16000);
    this.frameSize = Number(processorOptions.frameSize || 1280);
    this.pendingSamples = [];
    this.sourcePosition = 0;
  }

  process(inputs) {
    const input = inputs?.[0]?.[0];
    if (!input || input.length === 0) {
      return true;
    }

    const ratio = sampleRate / this.targetSampleRate;
    while (this.sourcePosition < input.length) {
      const sample = input[Math.floor(this.sourcePosition)] || 0;
      const clamped = Math.max(-1, Math.min(1, sample));
      this.pendingSamples.push(clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff);
      this.sourcePosition += ratio;
      if (this.pendingSamples.length >= this.frameSize) {
        this.postFrame();
      }
    }
    this.sourcePosition -= input.length;
    return true;
  }

  postFrame() {
    const frame = new Int16Array(this.pendingSamples.splice(0, this.frameSize));
    this.port.postMessage({ type: "pcm_frame", frame: frame.buffer }, [frame.buffer]);
  }
}

registerProcessor("wake-word-processor", WakeWordProcessor);
