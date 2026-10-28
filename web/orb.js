/* Dependency-free pseudo-3D holographic orb; no external tracking, GPU requirement or CDNs. */
(() => {
  'use strict';
  const canvas = document.getElementById('aura-canvas');
  const ctx = canvas.getContext('2d', {alpha:true});
  if (!ctx) return;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const orb = {mode:'idle', pulse:0};
  window.AuraOrb = {setMode(m){orb.mode=m;orb.pulse=1;}};
  let W=500,H=500,dpr=1,last=0,frame=0;
  let seed=729;
  const rand=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
  const dots=Array.from({length:145},()=>({theta:rand()*Math.PI*2,phi:Math.acos(2*rand()-1),size:rand()*1.7+.4,phase:rand()*6.28}));
  function resize(){const r=canvas.getBoundingClientRect();dpr=Math.min(window.devicePixelRatio||1,1.6);W=Math.max(100,r.width);H=Math.max(100,r.height);canvas.width=Math.round(W*dpr);canvas.height=Math.round(H*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);}
  new ResizeObserver(resize).observe(canvas);resize();
  const project=(theta,phi,r,rotation,cy)=>{
    let x=Math.sin(phi)*Math.cos(theta+rotation),z=Math.sin(phi)*Math.sin(theta+rotation),y=Math.cos(phi);
    const tilt=.25;let yy=y*Math.cos(tilt)-z*Math.sin(tilt),zz=y*Math.sin(tilt)+z*Math.cos(tilt);
    const persp=2.8/(2.8-zz*.4);
    return {x:W/2+x*r*persp,y:cy+yy*r*persp,z:zz};
  };
  function circle(x,y,r,stroke,lineWidth=1,alpha=1){ctx.beginPath();ctx.arc(x,y,r,0,2*Math.PI);ctx.strokeStyle=stroke;ctx.globalAlpha=alpha;ctx.lineWidth=lineWidth;ctx.stroke();ctx.globalAlpha=1;}
  function draw(timestamp){
    // Adaptive draw budget: keep voice interaction smooth, reduce idle CPU.
    // The hologram remains present; we only reduce redraw frequency.
    const frameDelay = reduced ? 500 : orb.mode === 'idle' ? 66 : orb.mode === 'thinking' ? 40 : 25;
    if (!document.hidden && (timestamp-last>=frameDelay)){
      last=timestamp;frame++;ctx.clearRect(0,0,W,H);
      const t=reduced?0:timestamp/1000;const k=Math.min(W,H)/500;const cx=W/2,cy=H*.465,r=132*k;
      const energy=orb.mode==='listening'?1.5:orb.mode==='thinking'?1.15:1;
      const breath=1+(!reduced?Math.sin(t*1.7)*.022:0);
      ctx.save();ctx.globalCompositeOperation='screen';
      const glow=ctx.createRadialGradient(cx,cy,8*k,cx,cy,220*k);
      glow.addColorStop(0,'rgba(84,234,255,.2)');glow.addColorStop(.34,'rgba(8,160,225,.13)');glow.addColorStop(.66,'rgba(8,105,183,.035)');glow.addColorStop(1,'rgba(8,104,173,0)');
      ctx.fillStyle=glow;ctx.beginPath();ctx.arc(cx,cy,220*k,0,Math.PI*2);ctx.fill();
      for(let ring=0;ring<4;ring++){
        const rr=r*(1.18+ring*.17)*breath;circle(cx,cy,rr,ring%2?'#4fd6ff':'#2b92ba',ring===0?1.3:.65,.14+Math.sin(t*.5+ring)*.045);
      }
      for(let layer=0;layer<3;layer++){
        ctx.save();ctx.translate(cx,cy);ctx.rotate(t*(layer%2?-.06:.08)+layer*1.1);ctx.scale(1,layer===0?.56:layer===1?.78:.36);
        ctx.beginPath();ctx.arc(0,0,r*(1.06+layer*.07)*breath,0,Math.PI*2);
        ctx.strokeStyle=layer===1?'rgba(78,215,255,.52)':'rgba(78,170,240,.3)';
        ctx.lineWidth=layer===1?1.7:.85;ctx.setLineDash(layer===1?[3*k,8*k]:[]);ctx.stroke();ctx.restore();
      }
      // Latitude and longitude wireframe arcs with perspective.
      const rot=t*.12;
      for(let lat=-1.0;lat<=1.05;lat+=.34){
        ctx.beginPath();for(let i=0;i<=85;i++){
          const th=i/85*Math.PI*2,phi=Math.PI/2+lat;
          const p=project(th,phi,r*breath,rot,cy);
          if(i===0)ctx.moveTo(p.x,p.y);else ctx.lineTo(p.x,p.y);
        }
        ctx.strokeStyle='rgba(55,183,238,.22)';ctx.lineWidth=.7;ctx.stroke();
      }
      for(let lon=0;lon<10;lon++){
        ctx.beginPath();for(let i=0;i<=75;i++){
          const phi=i/75*Math.PI,p=project(lon*2*Math.PI/10,phi,r*breath,rot,cy);
          if(i===0)ctx.moveTo(p.x,p.y);else ctx.lineTo(p.x,p.y);
        }
        ctx.strokeStyle='rgba(68,199,245,.19)';ctx.lineWidth=.8;ctx.stroke();
      }
      for(const d of dots){
        const p=project(d.theta,d.phi,r*breath,rot,cy);
        ctx.beginPath();ctx.arc(p.x,p.y,d.size*k*(.8+(p.z+1)*.24)*energy,0,Math.PI*2);
        ctx.fillStyle=`rgba(122,231,255,${.32+(p.z+1)*.22})`;ctx.fill();
      }
      const core=ctx.createRadialGradient(cx-15*k,cy-20*k,0,cx,cy,r*.86);
      core.addColorStop(0,`rgba(154,253,255,${.44*energy})`);
      core.addColorStop(.09,`rgba(65,215,255,${.33*energy})`);
      core.addColorStop(.28,`rgba(21,163,215,${.13*energy})`);
      core.addColorStop(.77,'rgba(18,123,215,.015)');core.addColorStop(1,'rgba(0,0,0,0)');
      ctx.fillStyle=core;ctx.beginPath();ctx.arc(cx,cy,r*.86,0,Math.PI*2);ctx.fill();
      for(let ring=0;ring<3;ring++){
        const a=t*(ring%2?-0.29:.2)+ring*1.6,sz=r*(1.31+ring*.16);
        ctx.beginPath();ctx.arc(cx,cy,sz,a,a+.35+Math.sin(t*.4+ring)*.09);
        ctx.lineWidth=(ring===0?2.4:1.4)*k;ctx.strokeStyle=ring===0?'rgba(152,246,255,.75)':'rgba(74,200,254,.5)';ctx.stroke();
      }
      // Small orbiting tracer, intentionally low cost.
      if(!reduced){let a=t*.4;let x=cx+Math.cos(a)*r*1.5,y=cy+Math.sin(a)*r*.63;circle(x,y,3*k,'#baf9ff',1,.8);}
      ctx.restore();orb.pulse*=.94;
    }
    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);
})();
