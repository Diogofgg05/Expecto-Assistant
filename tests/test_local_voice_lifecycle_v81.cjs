const test=require('node:test'),assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');

function mock(){
  let track, socket, timer=0; const deadlines=new Map();
  class WS{
    static CONNECTING=0;static OPEN=1;
    constructor(){socket=this;this.readyState=0;this.bufferedAmount=0;this.sent=[];}
    send(x){this.sent.push(x);}
    close(){this.readyState=3;this.onclose?.();}
  }
  class Audio{
    constructor(){this.sampleRate=48000;this.closed=false;}
    createMediaStreamSource(){return{connect(){},disconnect(){}};}
    createGain(){return{gain:{value:1},connect(){},disconnect(){}};}
    createScriptProcessor(){return{connect(){},disconnect(){}};}
    async close(){this.closed=true;}
  }
  const window={AudioContext:Audio};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/local-voice.js'),'utf8'),{
    window,WebSocket:WS,performance:{now:()=>0},location:{protocol:'http:',host:'localhost:8000'},
    navigator:{mediaDevices:{getUserMedia:async()=>{
      track={stopped:false,stop(){this.stopped=true;}};
      return{getTracks:()=>[track]};
    }}},
    fetch:async()=>({ok:true,json:async()=>({persistent_stt:true})}),
    AbortController,Blob,ArrayBuffer,DataView,Float32Array,Int16Array,
    setTimeout:(fn,ms)=>{deadlines.set(++timer,{fn,ms});return timer;},
    clearTimeout:id=>deadlines.delete(id)
  });
  return{voice:window.ExpectoLocalSTT,deadlines,socket:()=>socket,track:()=>track};
}
test('Whisper connection deadline cleans microphone without duplicate error',async()=>{
  const h=mock(),errors=[];
  assert.equal(await h.voice.start({onError:e=>errors.push(e.message)}),true);
  const pending=[...h.deadlines.values()].find(t=>t.ms===5000);
  assert.ok(pending);
  pending.fn();
  assert.equal(h.voice.active,false);
  assert.equal(h.track().stopped,true);
  assert.equal(errors.length,1);
  h.socket().onclose?.();
  assert.equal(errors.length,1);
  assert.equal(h.deadlines.size,0);
});
test('explicit cancel does not trigger a connection failure',async()=>{
  const h=mock(),errors=[];
  await h.voice.start({onError:e=>errors.push(e.message)});
  h.voice.cancel();
  assert.equal(h.voice.active,false);
  assert.equal(h.track().stopped,true);
  assert.equal(h.deadlines.size,0);
  assert.equal(errors.length,0);
});
