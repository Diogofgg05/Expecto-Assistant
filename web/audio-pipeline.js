/* EXPECTO 6.2 — stateful 16 kHz PCM capture + adaptive speech gate.
   All samples remain local. Audio chunks have no external dependencies. */
(() => {
  'use strict';
  class PCM16Resampler {
    constructor(inputRate) {
      if (!Number.isFinite(inputRate) || inputRate < 16000 || inputRate > 192000)
        throw new RangeError('Invalid microphone sample rate');
      this.rate=inputRate;
      this.position=0; // fractional position in the incoming stream
      this.previous=0; this.totalInput=0;
      this.outputCount=0;
    }
    push(input) {
      if (!input?.length) return new Int16Array(0);
      const step=this.rate/16000, start=this.totalInput;
      const end=start+input.length;
      const output=[];
      // Resample against absolute sample positions; preserves continuity at
      // AudioWorklet's 128-sample block boundaries (48k→16k).
      while (this.position < end) {
        const offset=this.position-start;
        const left=Math.floor(offset);
        const frac=offset-left;
        const a=left < 0 ? this.previous : input[Math.min(left,input.length-1)];
        const b=input[Math.min(Math.max(left+1,0),input.length-1)];
        const sample=Math.max(-1,Math.min(1,a+(b-a)*frac));
        output.push(sample<0?Math.round(sample*32768):Math.round(sample*32767));
        this.position+=step;
      }
      this.previous=input[input.length-1];
      this.totalInput=end;
      this.outputCount+=output.length;
      return Int16Array.from(output);
    }
  }
  class VoiceGate {
    constructor(sampleRate) {
      this.rate=sampleRate;
      this.noise=0.006;
      this.voicedMs=0;
      this.lastSpeechMs=null;
      this.startedMs=null;
      this.detected=false;
    }
    update(chunk, nowMs) {
      if(this.startedMs===null)this.startedMs=nowMs;
      let energy=0;
      for(let i=0;i<chunk.length;i++)energy+=chunk[i]*chunk[i];
      const rms=Math.sqrt(energy/Math.max(1,chunk.length));
      // Floor is estimated only from quiet samples and updated conservatively
      // to avoid learning speech as ambient noise.
      if(!this.detected && rms < Math.max(0.018,this.noise*2.5))
        this.noise=this.noise*0.97+rms*0.03;
      const threshold=Math.max(0.014, Math.min(0.065,this.noise*2.8));
      const active=rms>threshold;
      if(active){
        this.detected=true;
        this.voicedMs+=chunk.length/this.rate*1000;
        this.lastSpeechMs=nowMs;
      }
      const enough=this.voicedMs>=250;
      return {
        rms, threshold, speaking:active, voiced:enough,
        end:enough && this.lastSpeechMs!==null && nowMs-this.lastSpeechMs>=800,
        max:nowMs-this.startedMs>=15000,
      };
    }
  }
  window.ExpectoAudioDSP={PCM16Resampler,VoiceGate};
})();
