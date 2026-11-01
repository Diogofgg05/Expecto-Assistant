const {test}=require('node:test'), assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const context={window:{}};vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,'../web/audio-pipeline.js'),'utf8'),context);
const {PCM16Resampler,VoiceGate}=context.window.ExpectoAudioDSP;
test('resampling remains continuous across worklet frames',()=>{
 const samples=Float32Array.from({length:48000},(_,i)=>Math.sin(i*2*Math.PI/240));
 const r=new PCM16Resampler(48000);
 let count=0;
 for(let i=0;i<samples.length;i+=128)count+=r.push(samples.subarray(i,i+128)).length;
 assert.ok(count>=15999&&count<=16001);
});
test('gate learns room noise and recognizes speech and long pauses',()=>{
 const g=new VoiceGate(16000);let now=0,last=null;
 for(let i=0;i<40;i++){now+=20;last=g.update(new Float32Array(320).fill(.2),now)}
 assert.equal(last.voiced,true);
 for(let i=0;i<45;i++){now+=20;last=g.update(new Float32Array(320),now)}
 assert.equal(last.end,true);
});
