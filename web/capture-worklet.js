/* Audio thread: copy mono samples to main thread in small transferable blocks.
   Signal processing is intentionally minimal in the real-time callback. */
class ExpectoCaptureProcessor extends AudioWorkletProcessor {
  process(inputs, outputs) {
    const input=inputs[0];
    const channels=input?.length||0;
    if(channels){
      const frames=input[0].length;
      const data=new Float32Array(frames);
      for(let c=0;c<channels;c++){
        const samples=input[c];
        for(let i=0;i<frames;i++)data[i]+=samples[i]/channels;
      }
      this.port.postMessage(data,[data.buffer]);
    }
    const output=outputs[0];
    if(output) for(const channel of output) channel.fill(0);
    return true;
  }
}
registerProcessor('expecto-capture',ExpectoCaptureProcessor);
