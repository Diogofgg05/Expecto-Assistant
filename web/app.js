/* EXPECTO browser interface. No UI buttons, menus, routes, or remote scripts. */
(() => {
  'use strict';
  const app=document.getElementById('app');
  const workspace=document.getElementById('workspace');
  const stage=document.getElementById('aura-stage');
  const panels=document.getElementById('panels');
  const presence=document.getElementById('aura-presence');
  const transcript=document.getElementById('live-transcript');
  const shell=document.getElementById('command-shell');
  const input=document.getElementById('command-input');
  const clock=document.getElementById('clock');
  const state={panels:new Map(),busy:false,listening:false,recognition:null,
               localRecording:null,voiceFailure:null,abortController:null,history:[],sessionId:sessionStorage.getItem('aura_session_id')||'',voiceOutput:true,hideTranscript:null,width:43};
  if(!state.sessionId){state.sessionId=(window.crypto?.randomUUID?.()||Math.random().toString(36).slice(2));sessionStorage.setItem('aura_session_id',state.sessionId);}
  const LABELS={memory:'MEMÓRIA',research:'CONHECIMENTO',browser:'BROWSER · FONTES',
                jobs:'INVESTIGAÇÕES AUTÓNOMAS',mathematics:'MATEMÁTICA · CÁLCULO EXATO',patronum:'PATRONUM · NÚCLEO AVANÇADO',diagnostics:'DIAGNÓSTICOS',projects:'PROJETOS'};
  const setMode=(m)=>{app.classList.remove('listening','thinking','speaking');if(m!=='idle')app.classList.add(m);presence.textContent=({idle:'SISTEMA DISPONÍVEL',listening:'A OUVIR',thinking:'A PROCESSAR',speaking:'A RESPONDER'})[m]||m.toUpperCase();window.AuraOrb?.setMode(m);};
  function sayText(text,error=false){
    transcript.textContent=text||'';transcript.classList.toggle('error',error);
    transcript.classList.add('visible');clearTimeout(state.hideTranscript);
    state.hideTranscript=setTimeout(()=>transcript.classList.remove('visible'),Math.min(12500,4300+text.length*28));
  }
  function speech(text){
    if(!state.voiceOutput||!text||!('speechSynthesis' in window))return;
    try{
      speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text.slice(0,450));
      u.lang='pt-PT';u.rate=1.03;u.pitch=.94;
      const voices=speechSynthesis.getVoices();const pt=voices.find(v=>v.lang.toLowerCase()==='pt-pt')||voices.find(v=>v.lang.toLowerCase().startsWith('pt'));
      if(pt)u.voice=pt;
      u.onstart=()=>setMode('speaking');u.onend=()=>setMode('idle');u.onerror=()=>setMode('idle');
      speechSynthesis.speak(u);
    }catch(_){setMode('idle');}
  }
  function el(tag,cls,text){const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=String(text);return node;}
  function item(body,title,meta){const n=el('article','k-item');n.append(el('div','k-title',title));if(body)n.append(el('div','k-body',body));if(meta)n.append(el('div','k-meta',meta));return n;}
  function stat(parent,key,val){const d=el('div','stat');d.append(el('span','',key),el('strong','',val));parent.append(d);}
  function safeUrl(url){try{const parsed=new URL(url);return parsed.protocol==='https:'?parsed.href:null;}catch{return null;}}
  function loadPanel(name,data){
    const panel=state.panels.get(name);if(!panel)return;
    const body=panel.querySelector('.panel-body');body.replaceChildren();
    if(name==='mathematics'){
      if(!window.ExpectoMath?.render(body,data))body.append(el('div','panel-empty','Formato matemático indisponível.'));
    }else if(name==='patronum'){
      body.append(el('div','patronum-sigil','✦  EXPECTO PATRONUM  ✦'));
      stat(body,'MODO','ATIVO');stat(body,'OLLAMA',data?.ollama_available?'DISPONÍVEL':'NÃO DISPONÍVEL');
      stat(body,'MEMÓRIAS',String(data?.memories ?? 0));
      stat(body,'DOCUMENTOS',String(data?.documents ?? 0));
      stat(body,'MENSAGENS (6 MESES)',String(data?.conversations_6months ?? 0));
      body.append(el('div','k-meta','RECOMENDAÇÕES · NÃO SÃO AÇÕES EXECUTADAS'));
      for(const rec of (data?.recommendations||[]))body.append(item(rec,'ANÁLISE'));
    }else if(name==='memory'){
      if(!Array.isArray(data)||!data.length){body.append(el('div','panel-empty','Ainda não há memórias.\nDiz: “Lembra-te de que estou a criar a Expecto.”'));return;}
      for(const entry of data){body.append(item(entry.content,({preference:'PREFERÊNCIA',project:'PROJETO',fact:'FACTO',experience:'EXPERIÊNCIA',conversation:'CONVERSA',temporal:'ESTADO ATUAL',relation:'RELAÇÃO',summary:'SÍNTESE · FONTES',duplicate:'DUPLICADO POSSÍVEL',review:'REVISÃO',note:'MEMÓRIA'}[entry.category]||'MEMÓRIA'),`${(entry.updated_at||entry.created_at)?.replace('T',' ').slice(0,16)||''}   ID: ${entry.id}${entry.source==='auto_episode' ? ' · EXTRAÍDO DA CONVERSA '+(entry.evidence_episode_ids||'') : ''}`));}
    }else if(name==='research'||name==='browser'){
      const ds=Array.isArray(data)?data:(data?.documents||[]);
      if(data?.topic){body.append(el('div','k-meta','TEMA  /  '+data.topic));}
      if(data?.warning)body.append(el('div','warning',data.warning));
      if(Array.isArray(data?.claims)&&data.claims.length){
        body.append(el('div','k-meta','APRENDIZAGEM · HIPÓTESES, NÃO FACTOS COMPROVADOS'));
        for(const c of data.claims){
          const row=item(c.statement,`HIPÓTESE · ${(c.state||'single_source').toUpperCase()}`,
                         `${c.source_count||0} fontes · ID ${c.id}`);
          for(const source of (c.sources||[]).slice(0,3)){
            const safe=safeUrl(source.url||'');
            const line=el('div','k-meta',`“${source.exact_quote}” · ${source.source_host}`);
            if(safe){const a=el('a','',source.source_host);a.href=safe;a.target='_blank';a.rel='noopener noreferrer';line.append(' · ',a);}
            row.append(line);
          }
          body.append(row);
        }
      }
      // 3.3: factual rechecks are evidence reports, NOT fact certifications.
      if(data?.factcheck_report){
        const q=data.factcheck_report;
        body.append(el('div','k-meta','VERIFICAÇÃO FACTUAL · FONTES E INCERTEZA'));
        body.append(item(q.statement||'',`AVALIAÇÃO: ${(q.grade||'indeterminado').toUpperCase()}`,
          `ID ${q.claim_id||'—'} · Consulta ao vivo: ${q.live_attempted?'SIM':'NÃO'} · Prova: NÃO`));
        stat(body,'Fontes observadas ao vivo',q.live_supported_sources||0);
        stat(body,'Origens no arquivo local',q.unique_hosts_with_intact_snapshots||0);
        for(const source of (q.evidence||[]).slice(0,30)){
          body.append(item(source.comment||'',source.live_status||'não verificada',
                           `${source.host||'—'} · Arquivo: ${source.archive_integrity||'—'}`));
        }
        body.append(el('div','warning',q.limitations||'Citar uma fonte não comprova a verdade.'));
      }
      if(Array.isArray(data?.factcheck_history)){
        body.append(el('div','k-meta','HISTÓRICO DE VERIFICAÇÕES FACTUAIS'));
        for(const run of data.factcheck_history){
          body.append(item(run.created_at||'',run.grade||'Sem classificação',
                           `Hipótese ${run.claim_id||'—'} · Auditoria ${run.id||'—'}`));
        }
      }
      // Knowledge-quality reports reuse the same voice-opened research panel.
      // All output is text-only; no interactive navigation is inserted.
      if(data?.quality_report){
        const quality=data.quality_report;
        const reports=Array.isArray(quality.items)?quality.items:[quality];
        body.append(el('div','k-meta','QUALIDADE DAS EVIDÊNCIAS · AUDITORIA LOCAL'));
        if(typeof quality.checked==='number'){
          stat(body,'Hipóteses analisadas',quality.checked);
          stat(body,'Hipóteses retidas',quality.decisions?.withhold||0);
          stat(body,'Textos repetidos entre origens',quality.repeated_text_warnings||0);
          stat(body,'Revisões de arquivo pendentes',quality.review_due||0);
        }
        for(const q of reports.slice(0,40)){
          const state=q.decision==='withhold'?'NÃO REUTILIZAR':'HIPÓTESE COM RESERVAS';
          const text=[`Arquivo: ${q.snapshot_status||'—'}`,
            q.repeated_text_across_hosts?'Texto possivelmente republicado entre domínios':'',
            q.possible_math_conflicts?.length?`Conflitos aritméticos: ${q.possible_math_conflicts.join(', ')}`:'',
            q.review_due?'Revisão temporal recomendada':''].filter(Boolean).join(' · ');
          body.append(item(text,`${state} · ${q.grade||'sem classificação'}`,`ID ${q.claim_id}`));
        }
        body.append(el('div','warning','Auditoria apenas às cópias locais. Não certifica verdade nem verifica páginas ao vivo.'));
      }
      if(!ds.length){
        if(!data?.quality_report&&!data?.factcheck_report&&!data?.factcheck_history)body.append(el('div','panel-empty',name==='browser'?'Navegador de fontes.\nDiz: “Investiga sobre computação quântica.”':'Não existem fontes.\nDiz: “Aprende sobre redes neuronais.”'));
        return;
      }
      for(const doc of ds){
        const row=item((doc.content||'').slice(0,1300),doc.title||doc.topic,
                       `${doc.source_type||''} · ${doc.evidence_level||''} · ${doc.learned_at?.slice(0,10)||''}`);
        const link=safeUrl(doc.url||'');if(link){const title=row.querySelector('.k-title');title.replaceChildren();const a=el('a','',doc.title||doc.topic||'Fonte');a.href=link;a.target='_blank';a.rel='noopener noreferrer';title.append(a);}
        body.append(row);
      }
      if(name==='browser')body.append(el('div','k-meta','Leitor de fontes. Sites externos abrem no navegador habitual.'));
    }else if(name==='jobs'){
      if(!Array.isArray(data)||!data.length){body.append(el('div','panel-empty','Nenhuma investigação agendada.\nDiz: “Investiga autonomamente sobre inteligência artificial.”'));return;}
      for(const job of data){body.append(item(`Estado: ${job.enabled?'ATIVA':'DESATIVADA'} · Frequência: ${job.interval_hours} h`,job.topic,
                         `Última execução: ${job.last_run_at||'não iniciada'}${job.last_error?' · '+job.last_error:''}`));}
    }else if(name==='diagnostics'){
      const llm=data?.ollama||{};
      stat(body,'API EXPECTO','OPERACIONAL');stat(body,'Ollama',llm.available?'LIGADO':'INDISPONÍVEL');
      stat(body,'Modelo configurado',llm.selected||'—');stat(body,'Modelo instalado',llm.selected_installed?'SIM':'NÃO / DESCONHECIDO');
      stat(body,'Modelos detetados',llm.models?.join(', ')||'—');stat(body,'Memórias locais',data?.memory_count??'—');
      stat(body,'Mensagens (janela)',data?.episodes_6months??'—');stat(body,'Gravação automática',data?.episodic_capture?'ATIVA':'INATIVA');stat(body,'Meses de recordação',data?.memory_months??'—');
      stat(body,'Fontes guardadas',data?.knowledge_count??'—');stat(body,'Investigações ativas',data?.research_jobs??'—');
      stat(body,'Mensagens com embedding',data?.semantic_indexed??'—');stat(body,'Conhecimentos extraídos',data?.extracted_knowledge??'—');stat(body,'Extração automática',data?.extraction_active?'ATIVA':'DESATIVADA');
      stat(body,'Estados temporais (versões)',data?.temporal_facts??'—');
      stat(body,'Relações entre memórias',data?.relation_links??'—');
      stat(body,'Sínteses consolidadas',data?.consolidation?.summaries??'—');
      stat(body,'Fontes das sínteses',data?.consolidation?.linked_sources??'—');
      stat(body,'Modo privado',data?.private_mode?'ATIVO':'INATIVO');
      stat(body,'Backups cifrados',data?.encrypted_backups_enabled?'ATIVOS':'SEM FRASE-PASSE');
      stat(body,'Base SQLite ativa',data?.active_database_encrypted?'CIFRADA':'NÃO CIFRADA');
      stat(body,'Pesquisa pública',data?.research_provider||'Wikipedia');
      stat(body,'Ciclos de aprendizagem',data?.advanced_learning?.runs??'—');
      stat(body,'Evidências relacionadas',data?.advanced_learning?.evidence_links??'—');
      if(!llm.available)body.append(el('div','warning','Inicia o Ollama ou instala um modelo no terminal. Consulta o README.'));
    }else if(name==='projects'){
      body.append(el('div','panel-empty',data?.message||'Painel em desenvolvimento.'));
      for(const project of (data?.projects||[]))body.append(item('Projeto registado para demonstração.',project,''));
    }
  }
  function layout(){
    const len=state.panels.size;workspace.classList.toggle('has-panels',len>0);
    app.classList.toggle('idle',len===0);panels.hidden=len===0;
    panels.classList.toggle('multi',len===2);panels.classList.toggle('many',len>2);
    const width=window.innerWidth>760?(len===1?Math.min(55,state.width):len===2?35:28):100;
    workspace.style.setProperty('--aura-width',width+'%');
    if(len===0)state.width=43;
  }
  function openPanel(name,data){
    if(!(name in LABELS))return;
    let panel=state.panels.get(name);
    if(!panel){
      if(state.panels.size>=4){const oldest=state.panels.keys().next().value;closePanel(oldest);}
      panel=el('section','panel');panel.dataset.name=name;
      const header=el('div','panel-header');header.append(el('span','panel-title',LABELS[name]),el('span','panel-meta','EXPECTO / LIVE'));
      panel.append(header,el('div','panel-body'));panels.append(panel);state.panels.set(name,panel);
    }
    loadPanel(name,data);layout();
  }
  function closePanel(name){const p=state.panels.get(name);if(p){p.remove();state.panels.delete(name);}layout();}
  function closeAll(){for(const p of state.panels.values())p.remove();state.panels.clear();layout();}
  function respond(payload){
    if(payload?.data?.reasoning?.status==='exact_algebra'){
      openPanel('mathematics',payload.data.reasoning);
    }
    if(payload.action?.type==='patronum'){
      app.classList.add('patronum');openPanel('patronum',payload.data);
    }else if(payload.action?.type==='patronum_off'){
      app.classList.remove('patronum');closePanel('patronum');
    }else if(payload.action?.type==='close_all'){app.classList.remove('patronum');closeAll();}
    else if(payload.action?.type==='close')closePanel(payload.action.panel);
    else if(payload.action?.type==='open')openPanel(payload.action.panel,payload.data);
    else if(payload.action?.type==='resize'){
      state.width=payload.action.size==='large'?24:55;layout();
    }else if(payload.action?.type==='move'){
      const p=state.panels.get(payload.action.panel);if(p){panels.append(p);state.panels.delete(payload.action.panel);state.panels.set(payload.action.panel,p);}
    }
    if(payload.text)sayText(payload.text);
    if(payload.spoken)speech(payload.spoken);else setMode('idle');
  }
  async function send(command){
    if(state.busy)return;
    const msg=(command||'').trim();if(!msg)return;
    state.busy=true;setMode('thinking');sayText('A analisar: '+msg);
    shell.hidden=true;input.blur();
    const controller=new AbortController();state.abortController=controller;
    const request={message:msg,history:state.history.slice(-6),session_id:state.sessionId};
    let payload=null,preview='',lastFrame=0;
    try{
      const headers={'Content-Type':'application/json'};
      let res=await fetch('/api/command/stream',{method:'POST',headers,
        body:JSON.stringify(request),signal:controller.signal});
      if(res.status===404){
        // Backward-compatible local server: no fake streaming for legacy API.
        res=await fetch('/api/command',{method:'POST',headers,
          body:JSON.stringify(request),signal:controller.signal});
        if(!res.ok)throw new Error('HTTP '+res.status);
        payload=await res.json();
      }else{
        if(!res.ok)throw new Error('HTTP '+res.status);
        if(!res.body?.getReader)throw new Error('O navegador não suporta streaming HTTP.');
        const reader=res.body.getReader(),decoder=new TextDecoder();
        let pending='';
        while(true){
          const {value,done}=await reader.read();
          if(done)break;
          pending+=decoder.decode(value,{stream:true});
          if(pending.length>64000)throw new Error('Fluxo de resposta inválido.');
          const frames=pending.split(/\r?\n\r?\n/);
          pending=frames.pop();
          for(const frame of frames){
            const line=frame.split(/\r?\n/).find(x=>x.startsWith('data: '));
            if(!line)continue;
            const event=JSON.parse(line.slice(6));
            if(event.type==='token'){
              preview+=String(event.text||'');
              if(preview.length>12000)throw new Error('Resposta demasiado longa.');
              const now=performance.now();
              if(now-lastFrame>=80){
                sayText('RASCUNHO · sujeito a verificação\n'+preview);
                lastFrame=now;
              }
            }else if(event.type==='final'){
              payload=event.payload;
            }else if(event.type==='error'){
              throw new Error(event.message||'Falha na geração.');
            }
          }
        }
        if(!payload)throw new Error('A ligação terminou antes da resposta final.');
      }
      respond(payload);
      state.history.push({role:'user',content:msg},{role:'assistant',content:payload.text||''});
      state.history=state.history.slice(-10);
    }catch(err){
      setMode('idle');
      sayText(controller.signal.aborted?'Pedido interrompido.':
        'Sem ligação à Expecto. Verifica se o servidor está iniciado. ('+err.message+')',!controller.signal.aborted);
    }finally{
      state.busy=false;
      if(state.abortController===controller)state.abortController=null;
    }
  }
  function edit(){shell.hidden=false;input.focus();}
  function voiceErrorMessage(code){
    const details={
      network:'O serviço de reconhecimento do navegador falhou (network). Podes ativar o reconhecimento local offline; o áudio não será enviado a terceiros.',
      'not-allowed':'Permissão do microfone recusada. Autoriza o microfone nas definições do navegador para localhost.',
      'service-not-allowed':'O reconhecimento de voz do navegador foi bloqueado.',
      'audio-capture':'Microfone indisponível. Verifica o dispositivo de entrada no Windows.',
      'no-speech':'Não foi detetada voz. Experimenta novamente.',
      aborted:'Reconhecimento interrompido.'
    };
    return details[code]||'Falha no reconhecimento ('+code+'). Usa / para escrever.';
  }
  async function captureLocalVoice(){
    if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){
      sayText('Este navegador não permite gravar áudio localmente. Usa localhost e verifica as permissões.',true);return;
    }
    if(!window.isSecureContext){sayText('O microfone exige uma origem segura (localhost ou HTTPS).',true);return;}
    let stream;
    try{
      stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
      const mime=['audio/webm;codecs=opus','audio/webm','audio/ogg','audio/mp4'].find(x=>MediaRecorder.isTypeSupported(x));
      if(!mime){stream.getTracks().forEach(x=>x.stop());sayText('Formato de áudio não suportado pelo navegador.',true);return;}
      const recorder=new MediaRecorder(stream,{mimeType:mime});
      const chunks=[];
      let size=0;
      const stopTimer=setTimeout(()=>{if(recorder.state==='recording')recorder.stop();},14000);
      const capture={recorder,stream,stopTimer};state.localRecording=capture;
      recorder.ondataavailable=e=>{
        if(e.data?.size){size+=e.data.size;if(size<=8*1024*1024)chunks.push(e.data);}
        if(size>8*1024*1024&&recorder.state==='recording')recorder.stop();
      };
      recorder.onerror=()=>sayText('Falhou a captura de áudio. Verifica as permissões do microfone.',true);
      recorder.onstop=async()=>{
        clearTimeout(stopTimer);stream.getTracks().forEach(x=>x.stop());state.localRecording=null;state.listening=false;
        if(size>8*1024*1024){setMode('idle');sayText('O áudio excede o limite de 8 MB.',true);return;}
        if(!chunks.length){setMode('idle');sayText('Não foi capturado áudio.',true);return;}
        setMode('thinking');sayText('A transcrever localmente…');
        try{
          const result=await fetch('/api/voice/transcribe',{method:'POST',headers:{'Content-Type':mime.split(';')[0]},body:new Blob(chunks,{type:mime})});
          if(!result.ok)throw new Error('Transcrição indisponível (HTTP '+result.status+').');
          const data=await result.json();if(data.text?.trim())await send(data.text);
          else{setMode('idle');sayText('Não foi identificada fala. Tenta novamente.');}
        }catch(err){setMode('idle');sayText('Voz local: '+err.message,true);}
      };
      recorder.start(250);state.listening=true;setMode('listening');
      sayText('A ouvir localmente… pressiona V para terminar (máximo 14 s).');
    }catch(err){
      stream?.getTracks().forEach(x=>x.stop());state.listening=false;setMode('idle');
      sayText('Microfone: '+(err.name==='NotAllowedError'?'permissão recusada':err.message)+'.',true);
    }
  }
  async function voice(){
    if(state.busy)return;
    if(state.localRecording){if(state.localRecording.recorder.state==='recording')state.localRecording.recorder.stop();return;}
    if(state.listening){state.recognition?.stop();return;}
    window.speechSynthesis?.cancel();
    // An explicitly configured offline model avoids the Web Speech network
    // backend and keeps audio on this same-origin localhost server.
    let local=false;
    try{const r=await fetch('/api/voice/diagnostics');if(r.ok)local=!!(await r.json()).configured;}catch(_){}
    if(local){await captureLocalVoice();return;}
    const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
    if(!Recognition){sayText('Este navegador não suporta SpeechRecognition. Configura voz local ou usa / para escrever.',true);return;}
    const rec=new Recognition();state.recognition=rec;
    rec.lang='pt-PT';rec.interimResults=true;rec.continuous=false;
    let final='',failure='';
    rec.onstart=()=>{state.listening=true;setMode('listening');sayText('Estou a ouvir…');};
    rec.onresult=(event)=>{
      let partial='';for(let i=event.resultIndex;i<event.results.length;i++){
        const content=event.results[i][0].transcript;
        if(event.results[i].isFinal)final+=content+' ';else partial+=content+' ';
      }
      sayText((final+partial).trim()||'Estou a ouvir…');
    };
    rec.onerror=(event)=>{
      failure=event.error||'unknown';
      if(failure!=='aborted'&&failure!=='no-speech')sayText(voiceErrorMessage(failure),true);
    };
    rec.onend=()=>{
      state.listening=false;state.recognition=null;setMode('idle');
      const command=final.trim();
      if(command)send(command);
      else if(failure==='network')sayText(voiceErrorMessage('network'),true);
    };
    try{rec.start();}catch(err){
      state.listening=false;state.recognition=null;setMode('idle');
      sayText('Não foi possível iniciar o reconhecimento: '+err.message,true);
    }
  }
  document.addEventListener('keydown',(e)=>{
    if(e.ctrlKey||e.altKey||e.metaKey)return;
    if(e.target===input){
      if(e.key==='Enter'){e.preventDefault();const text=input.value;input.value='';send(text);}
      if(e.key==='Escape'){e.preventDefault();shell.hidden=true;input.value='';input.blur();}
      return;
    }
    if(e.key==='/'){e.preventDefault();edit();}
    if(e.key.toLowerCase()==='v'&&!e.repeat){e.preventDefault();voice();}
    if(e.key==='Escape'){
      e.preventDefault();
      state.abortController?.abort();
      if(state.localRecording?.recorder?.state==='recording')state.localRecording.recorder.stop();
      state.recognition?.abort();
      closeAll();window.speechSynthesis?.cancel();setMode('idle');sayText('Modo central.');
    }
  });
  function renderClock(){const d=new Date();clock.textContent=d.toLocaleTimeString('pt-PT',{hour:'2-digit',minute:'2-digit'});}
  renderClock();setInterval(renderClock,10000);
  fetch('/api/config').then(r=>r.json()).then(x=>{state.voiceOutput=!!x.voice_output;}).catch(()=>{});
  window.addEventListener('beforeunload',()=>window.speechSynthesis?.cancel());
  window.AuraUI={send,openPanel,closeAll}; // Exposed for local accessibility / developer tests.
})();
