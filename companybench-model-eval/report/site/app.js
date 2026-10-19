const D=/*__DATA__*/null;
const S=D.subject, M=D.models, L=D.label, OT=M.filter(m=>m!==S), NM=M.length;
const COL={};M.forEach((m,i)=>COL[m]='var(--c'+i+')');
const DOT=' &middot; ';
const $=s=>document.querySelector(s), fmt=(x,d=0)=>Number(x).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
const pct=(a,b)=>b?fmt(100*a/b,1)+'%':'n/a';
const sum=a=>a.reduce((x,y)=>x+y,0);
const ORD=['','first','second','third','fourth','fifth','sixth','seventh','eighth','ninth','tenth'];
const ord=n=>ORD[n]||n+'th';
const rank=(m,f,hi)=>1+M.filter(x=>hi?f(x)>f(m):f(x)<f(m)).length;
const rng=(f,d=0)=>{const v=OT.map(f).filter(x=>x!=null&&!isNaN(x));if(!v.length)return 'n/a';const a=Math.min(...v),b=Math.max(...v);return fmt(a,d)===fmt(b,d)?fmt(a,d):fmt(a,d)+' to '+fmt(b,d)};
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const runBy={};D.runs.forEach(r=>runBy[r.key]=r);
const color=r=>r>=0.9999?'var(--good)':r>=0.5?'var(--mid)':'var(--bad)';
const T=a=>D.tasks[a].title;
const RD=D.reader||{}, NOTES=RD.notes||{}, CARDS=RD.cards||{}, RCARDS=RD.rcards||{};
const RER=D.rerun_models, RERUN=RER.length>0, SUBRER=RER.includes(S);
const NT=Object.keys(D.tasks).length, NK=D.keep.length, N80=D.V['80'][S].n;
const WY=D.why||{}, LT=D.lt||{};
const short=m=>m;
let VIEW='80';
const VV=()=>VIEW==='80'?D.V['80']:D.V.same;
const sub80=D.runs.filter(r=>r.model===S&&r.view==='80');
const longOf={};D.runs.filter(r=>r.view==='long').forEach(r=>longOf[r.replaces]=r);
const subMiss80=sub80.filter(r=>r.reward<0.9999);
const subMissLong=sub80.filter(r=>D.keep.includes(r.alias)).map(r=>longOf[r.key]||r).filter(r=>r.reward<0.9999);
let subMiss=subMiss80;
const modeOf=k=>(CARDS[k]||RCARDS[k]||{}).mode||D.modes[k]||'Not labelled';
const bestOther=(alias)=>D.runs.filter(x=>x.alias===alias&&x.model!==S&&x.view==='80').sort((x,y)=>y.reward-x.reward||x.turns-y.turns)[0];
const taskMean=(alias,m)=>{const v=D.matrix.find(x=>x.alias===alias).cells[m].map(x=>x[1]);return v.reduce((a,b)=>a+b,0)/Math.max(1,v.length)};

function lede(){
  const a=D.V['80'], s=D.V.same, tos=a[S].timeouts, oto=sum(OT.map(m=>a[m].timeouts)), on=sum(OT.map(m=>a[m].n));
  $('#h1').textContent=L[S]+' on Turing CompanyBench';
  $('#eyebrow').innerHTML='Turing CompanyBench'+DOT+NT+' long-horizon company tasks'+DOT+M.map(m=>esc(L[m])).join(', ')+DOT+'3 runs each'+DOT+'same Terminus 2 agent harness'+DOT+'<a href="#method" style="color:inherit">how runs work</a>';
  let t=`Given the same 80 minutes, ${L[S]} reaches full marks in ${a[S].full} of ${N80} runs, against ${OT.map(m=>a[m].full+' for '+L[m]).join(', ')}. Its mean score is ${fmt(a[S].mean,3)}, ${ord(rank(S,m=>a[m].mean,1))} of ${NM}. ${tos} of its ${N80} runs hit the 80 minute limit${a[S].zero?' and '+a[S].zero+' scored zero':''}; across the other models, ${oto} of ${on} did.`;
  if(SUBRER&&s[S].n)t+=` Rerun with up to 5 hours, on the ${NK} of ${NT} tasks where every rerun finished, ${L[S]} reaches full marks in ${s[S].full} of ${s[S].n} runs, against ${OT.map(m=>s[m].full+' for '+L[m]).join(', ')}. ${RER.length===1?'Only '+L[S]+' was rerun':RER.map(m=>L[m]).join(' and ')+' were rerun'}, and the tasks with an unfinished rerun are left out for every model.`;
  $('#lede').textContent=t;
  const k=[[`${tos} of ${N80}`,`${L[S]} runs that hit the 80 minute limit (others: ${oto} of ${on})`],[`${a[S].full} of ${N80}`,`${L[S]} full marks at 80 minutes (best other: ${Math.max(...OT.map(m=>a[m].full))})`]];
  if(SUBRER&&s[S].n)k.push([`${s[S].full} of ${s[S].n}`,`${L[S]} full marks with up to 5 hours on the ${NK} tasks whose reruns finished (best other: ${Math.max(...OT.map(m=>s[m].full))})`]);
  else k.push([`${fmt(a[S].minutes,0)} min`,`${L[S]} mean per run, against ${rng(m=>a[m].minutes,0)} for the others`]);
  $('#kpis').innerHTML=k.map(x=>`<div class="kpi"><b>${x[0]}</b><span>${esc(x[1])}</span></div>`).join('');
}
function results(){
  const V=VV(), n=V[S].n;
  const rF=rank(S,m=>V[m].full,1), rM=rank(S,m=>V[m].mean,1);
  $('#resh').textContent=(VIEW==='80'?'At 80 minutes ':`With up to 5 hours, on the ${NK} tasks whose reruns finished, `)+`${L[S]} is ${ord(rF)} of ${NM} on full marks (${V[S].full} of ${n}) and ${ord(rM)} on mean score (${fmt(V[S].mean,3)}).`;
  $('#resnote').textContent=VIEW==='80'?`${N80} runs per model, all ${NT} tasks, same 80 minute limit.`:`${NK} of ${NT} tasks, ${n} runs per model. Models that were not rerun keep their 80 minute runs; their totals change only because ${D.drop.length} task${D.drop.length===1?'':'s'} whose rerun had not finished ${D.drop.length===1?'is':'are'} dropped for every model. Sensitivity, all ${NT} tasks with unfinished reruns scored 0: ${L[S]} ${D.V.sens0[S].full} of ${D.V.sens0[S].n} full marks, mean ${fmt(D.V.sens0[S].mean,3)}.`;
  let h=`<div class="eyebrow">Full marks, of ${n} runs</div>`;
  M.forEach(m=>h+=`<div class="bar"><span>${esc(L[m])}</span><span class="track"><span class="fill" style="width:${100*V[m].full/n}%;background:${COL[m]}"></span></span><span class="num">${V[m].full}${DOT}${pct(V[m].full,n)}</span></div>`);
  h+='<div class="eyebrow" style="margin-top:6px">Mean score, 0 to 1</div>';
  M.forEach(m=>h+=`<div class="bar"><span>${esc(L[m])}</span><span class="track"><span class="fill" style="width:${100*V[m].mean}%;background:${COL[m]}"></span></span><span class="num">${fmt(V[m].mean,3)}</span></div>`);
  $('#bars').innerHTML=h;
  const rows=[['Full marks',m=>`${V[m].full} of ${n}`,m=>V[m].full,1],['Mean score',m=>fmt(V[m].mean,3),m=>V[m].mean,1],['Runs with partial credit',m=>`${V[m].partial} of ${n}`,m=>V[m].partial,0],['Runs scoring zero',m=>`${V[m].zero} of ${n}`,m=>V[m].zero,-1],['Tool calls per run',m=>fmt(V[m].tool_calls,1),m=>V[m].tool_calls,-1],['Agent steps per run',m=>fmt(V[m].turns,1),m=>V[m].turns,-1],['Minutes per run',m=>fmt(V[m].minutes,1),m=>V[m].minutes,-1],['90th percentile minutes',m=>fmt(V[m].p90_min,1),m=>V[m].p90_min,-1],['Input tokens per run',m=>fmt(V[m].in_tok/1e6,2)+' M',m=>V[m].in_tok,-1],['Output tokens per run',m=>fmt(V[m].out_tok/1e3,1)+' k',m=>V[m].out_tok,-1],['Cost per run',m=>'$'+fmt(V[m].cost,2),m=>V[m].cost,-1],['Cost per full-marks run',m=>V[m].cost_per_full==null?'n/a':'$'+fmt(V[m].cost_per_full,2),m=>V[m].cost_per_full==null?Infinity:V[m].cost_per_full,-1]];
  $('#eff').innerHTML='<thead><tr><th></th>'+M.map(m=>`<th><span class="dot" style="background:${COL[m]}"></span>${esc(L[m])}</th>`).join('')+'</tr></thead><tbody>'+rows.map(([k,f,v,dir])=>{const vals=M.map(v),fin=vals.filter(isFinite),best=dir===0?null:dir>0?Math.max(...fin):Math.min(...fin),worst=dir===0?null:dir>0?Math.min(...fin):Math.max(...fin);return `<tr><td>${k}</td>`+M.map((m,i)=>`<td class="num${vals[i]===best?' best':vals[i]===worst?' worst':''}">${f(m)}</td>`).join('')+'</tr>'}).join('')+'</tbody><caption class="foot" style="caption-side:bottom;text-align:left;padding-top:6px">Green best, red worst in each row. Cost is the model usage cost the evaluation platform records per run (sandbox cost excluded), not audited against list prices.</caption>';
}
function timeSection(){
  const a=D.V['80'], tos=a[S].timeouts, oto=sum(OT.map(m=>a[m].timeouts)), on=sum(OT.map(m=>a[m].n));
  $('#timeh').textContent=`${tos} of ${L[S]}'s ${N80} runs hit the 80 minute limit; ${oto} of the other ${on} did.`;
  const li=[], to=sub80.filter(r=>r.timeout), ok=sub80.filter(r=>!r.timeout), mean=x=>x.length?sum(x.map(r=>r.reward))/x.length:0;
  if(to.length)li.push(`The ${to.length} runs that hit the limit sit on ${new Set(to.map(r=>r.alias)).size} of ${NT} tasks and average ${fmt(mean(to),2)}. The other ${ok.length} runs average ${fmt(mean(ok),2)}.`);
  const wsh=x=>{const w=sum(x.map(r=>r.wait_s||0)),t=sum(x.map(r=>r.agent_min*60));return t?100*w/t:null};
  const wt=wsh(to.length?to:sub80);
  if(wt!=null)li.push(`The model asked the terminal to wait for about ${fmt(wt,0)}% of the agent time${to.length?' in those runs':''}; the rest is the model generating. Provider speed cannot be separated from model behaviour: there are no provider-side logs.`);
  const tps=m=>{const v=D.runs.filter(r=>r.model===m&&r.view==='80'&&r.agent_min&&r.out_tok).map(r=>r.out_tok/(r.agent_min*60)).sort((x,y)=>x-y);return v.length?v[Math.floor(v.length/2)]:null};
  li.push(`Output per second of agent time (median run): ${fmt(tps(S),1)} tokens against ${rng(tps,1)} for the others. Output tokens per run: ${fmt(a[S].out_tok/1000)}k against ${rng(m=>a[m].out_tok/1000)}k.`);
  const w=WY[S], wto=WY[S+'_timeout'], wfin=WY[S+'_finished'], l=LT[S];
  if(w){li.push(`Median output per turn: ${w.median_tokens_per_turn} tokens${wto&&wfin?` (${wto.median_tokens_per_turn} in runs that hit the limit, ${wfin.median_tokens_per_turn} in runs that finished)`:''}, against ${rng(m=>(WY[m]||{}).median_tokens_per_turn)} for the others.`);
    if(l)li.push(`Turns of 8,000 or more output tokens: ${fmt(l.long_turns_per_run,2)} per run, against ${rng(m=>(LT[m]||{}).long_turns_per_run,2)}. ${fmt(100*w.time_share_in_8k_turns,0)}% of the clock goes to them, against ${rng(m=>100*(WY[m]||{}).time_share_in_8k_turns,0)}%.`);
    li.push(`${fmt(100*w.recheck_share,1)}% of turns open with a re-check phrase such as "wait" or "hold on" (a word-pattern count), against ${rng(m=>100*(WY[m]||{}).recheck_share,1)}% for the others.`);}
  if(l)li.push(`Re-check cycles (a stretch of turns that re-opens a result without delivering): ${fmt(l.cycles_per_run,2)} per run, against ${rng(m=>(LT[m]||{}).cycles_per_run,2)}${l.cycles?`; median ${l.cycle_turns_median} turns (${fmt(l.cycle_minutes_median,0)} min), longest ${l.cycle_turns_max} turns (${fmt(l.cycle_minutes_max,0)} min)`:''}. Steps from the first data query to the first deliverable (median): ${l.steps_query_to_delivery_median} against ${rng(m=>(LT[m]||{}).steps_query_to_delivery_median)}.`);
  $('#timelist').innerHTML=li.map(x=>`<li>${esc(x)}</li>`).join('');
}
function longpanel(){
  if(!RERUN){$('#longpanel').style.display='none';$('#ltab').innerHTML='';return}
  const out=[];
  RER.forEach(m=>{const s=D.lsum[m], pend=s.pending||0;
    out.push(`${L[m]}: ${s.n} of ${s.slots} reruns finished by the cutoff; ${s.full} reached full marks, mean ${fmt(s.mean,3)}.`,
    `${s.n-s.over80} of ${s.n} finished inside 80 agent minutes this time (median ${fmt(s.agent_median,0)}); ${s.over80} needed longer, up to ${fmt(s.max_agent,0)}; ${pend} more ${pend===1?'was':'were'} still running at the cutoff.`,
    `Turns of 8,000 or more output tokens: ${pct(s.orig_turns8k,s.orig_turns_all)} of turns in the timed-out originals, ${pct(s.turns8k,s.turns_all)} in the reruns. Median turns per run: ${fmt(s.orig_turns_median,0)} in the originals, ${fmt(s.turns_median,0)} in the reruns.`)});
  out.push('Two runs per slot is two draws; it does not give a per-task rate.');
  $('#longlist').innerHTML=out.map(x=>`<li>${esc(x)}</li>`).join('');
  const m0=SUBRER?S:RER[0], rr=D.runs.filter(r=>r.view==='long'&&r.model===m0).sort((a,b)=>a.key<b.key?-1:1);
  $('#ltab').innerHTML='<thead><tr><th>Slot</th><th>Task</th><th>80 min turns</th><th>Largest turn</th><th>Rerun score</th><th>Rerun minutes</th><th>Rerun turns</th><th>Largest turn</th><th></th></tr></thead><tbody>'+rr.map(r=>{const o=runBy[r.replaces];return `<tr><td class="num">${r.alias} run ${r.cell}</td><td class="l">${esc(T(r.alias))}</td><td class="num">${o.turns}</td><td class="num">${fmt(o.max_turn_tokens)}</td><td class="num">${fmt(r.reward,2)}</td><td class="num">${fmt(r.agent_min,0)}</td><td class="num">${r.turns}</td><td class="num">${fmt(r.max_turn_tokens)}</td><td><button class="link" data-k="${o.key}">original</button>${DOT}<button class="link" data-k="${r.key}">rerun</button></td></tr>`}).join('')+'</tbody>';
}
const NEXTTXT={'query data':'another query of the data','read company system':'another read of a company system','wait':'a wait','run script':'another script run','read file':'another file read','write script':'another script written','deliver':'the deliverable'};
function ltxHTML(){
  const rows=[];
  sub80.filter(r=>r.timeout&&(D.ltr[r.key]||[]).length).sort((a,b)=>b.max_turn_tokens-a.max_turn_tokens).slice(0,4).forEach(r=>{
    const big=D.ltr[r.key].slice().sort((x,y)=>y.tokens-x.tokens)[0], rowm=D.matrix.find(x=>x.alias===r.alias);
    const peers=OT.map(m=>{const rs=rowm.cells[m].map(c=>runBy[c[0]]);return {m,full:rs.filter(x=>x.reward>=0.9999).length,lo:Math.min(...rs.map(x=>x.minutes)),hi:Math.max(...rs.map(x=>x.minutes)),big:Math.max(...rs.map(x=>x.max_turn_tokens))}}).sort((x,y)=>y.full-x.full)[0];
    rows.push({k:r.key,t:big.topic,task:T(r.alias),turn:`Turn ${big.turn} of ${r.turns}: about ${fmt(Math.round(big.tokens/1000)*1000)} output tokens over ${fmt(big.secs/60,0)} minutes.`,next:`The next action was ${NEXTTXT[big.next]||big.next}. The run hit the 80 minute limit after ${r.turns} turns.`,peer:peers?`${L[peers.m]}: full marks in ${peers.full} of 3 runs, ${fmt(peers.lo,0)} to ${fmt(peers.hi,0)} minutes; its largest turn was ${fmt(peers.big)} tokens.`:''})});
  if(!rows.length)return '';
  return `<div class="ltx">${rows.map(e=>`<div class="ltxc"><div class="ltxh"><b>${esc(e.task)}</b><span class="chip">${esc(e.t)}</span></div><p>${esc(e.turn)}</p><p>${esc(e.next)}</p><p class="cl">${esc(e.peer)}</p><button class="link" data-k="${e.k}">Open this run in the trace player</button></div>`).join('')}</div>`}
function sbs(){
  const R=RD.sbs;
  if(R&&R.tasks&&R.tasks.length){
    const b=R.summary||[], bet=b.filter(x=>x.argon==='better').map(x=>x.behaviour), wor=b.filter(x=>x.argon==='worse').map(x=>x.behaviour);
    $('#sbsh').textContent=`${L[S]}: where it is better and where it is worse.`;
    $('#sbsp').innerHTML=`<b>Better</b>: ${esc(bet.join('; '))}. <b>Worse</b>: ${esc(wor.join('; '))}.`;
    $('#sbsfoot').textContent='Each comparison reads one run of the subject model against one run of another model on the same task, at the step where they part ways; each row of the table names the tasks it rests on (one reader\'s judgement per run pair). Open either trace.';
    $('#behav').innerHTML='<thead><tr><th>Behaviour</th><th>'+esc(short(S))+'</th><th>Tasks</th><th class="l">What we saw</th></tr></thead><tbody>'+b.map(x=>`<tr><td class="l">${esc(x.behaviour)}</td><td><span class="tag ${x.argon}">${esc(x.argon)}</span></td><td class="num">${(x.tasks||[]).join(', ')}</td><td class="l">${esc(x.explain)}</td></tr>`).join('')+'</tbody>';
    const order=R.tasks.slice().sort((a,b)=>a.side===b.side?(a.alias<b.alias?-1:1):(a.side==='ahead'?-1:1));
    $('#sbslist').innerHTML=order.map(t=>{const pk=t.peer_key||'',pm=pk.split('-')[1]||'';const pl=M.filter(m=>m.toLowerCase()===pm).map(m=>L[m])[0]||pm;
      return `<details class="card"><summary><span class="tag ${t.side==='ahead'?'better':'worse'}">${t.side==='ahead'?esc(short(S))+' better':esc(short(S))+' worse'}</span><b>${t.alias}</b><span>${esc(T(t.alias))}</span><span class="foot">${esc(t.better_or_worse||'')}</span></summary>
      <div style="display:grid;gap:8px;padding-top:8px;font-size:13.5px"><p class="foot">${esc(t.kind||'')}</p>
      <div class="vs"><div><span class="eyebrow">${esc(L[S])}</span><p>${esc(t.argon)}</p><button class="link" data-k="${t.argon_key}" data-s="${t.diverge_step_argon||''}">Open at step ${t.diverge_step_argon||1}</button></div>
      <div><span class="eyebrow">${esc(pl)}</span><p>${esc(t.peer)}</p><button class="link" data-k="${pk}" data-s="${t.diverge_step_peer||''}">Open at step ${t.diverge_step_peer||1}</button></div></div>
      <p><b>Why:</b> ${esc(t.why)}</p>${t.checks?`<p class="foot">Checks: ${esc(t.checks)}</p>`:''}</div></details>`}).join('');
    return}
  $('#sbsh').textContent=`Where ${L[S]} and the best other model part ways.`;
  $('#sbsp').textContent='For each task, the subject model is set against the other model with the highest mean score on that task. The ten tasks with the widest gap in either direction are listed, with both runs one click away.';
  $('#sbsfoot').textContent='Automatic pairs from the run data: no one has read these traces yet. A reader pass (README step 9) adds a written read of each pair at the step where the runs part ways.';
  const rows=D.matrix.map(row=>{let bm=null,bv=-1;OT.forEach(m=>{const v=taskMean(row.alias,m);if(v>bv){bv=v;bm=m}});const sv=taskMean(row.alias,S);return {row,bm,bv,sv,gap:sv-bv}}).sort((a,b)=>Math.abs(b.gap)-Math.abs(a.gap)).slice(0,10);
  $('#behav').innerHTML='<thead><tr><th>Task</th><th>'+esc(short(S))+' mean</th><th>Best other</th><th>Its mean</th><th>Minutes per run (subject, other)</th><th>Turns per run (subject, other)</th><th></th></tr></thead><tbody>'+rows.map(x=>{const sr=x.row.cells[S].map(c=>runBy[c[0]]),or=x.row.cells[x.bm].map(c=>runBy[c[0]]);const av=(a,f)=>sum(a.map(f))/Math.max(1,a.length);const worst=sr.slice().sort((a,b)=>a.reward-b.reward)[0],best=or.slice().sort((a,b)=>b.reward-a.reward)[0];
    return `<tr><td class="l"><b class="num">${x.row.alias}</b> ${esc(x.row.title)}</td><td class="num">${fmt(x.sv,2)}</td><td>${esc(L[x.bm])}</td><td class="num">${fmt(x.bv,2)}</td><td class="num">${fmt(av(sr,r=>r.minutes),0)}, ${fmt(av(or,r=>r.minutes),0)}</td><td class="num">${fmt(av(sr,r=>r.turns),0)}, ${fmt(av(or,r=>r.turns),0)}</td><td><button class="link" data-k="${worst.key}">open ${esc(short(S))} run ${worst.cell}</button>${DOT}<button class="link" data-k="${best.key}">open ${esc(short(x.bm))} run ${best.cell}</button></td></tr>`}).join('')+'</tbody>';
  $('#sbslist').innerHTML='';
}
function modes(){
  const c={};subMiss.forEach(r=>{const m=modeOf(r.key);(c[m]=c[m]||[]).push(r)});
  const ks=Object.keys(c).sort((a,b)=>c[b].length-c[a].length);
  const X={};((RD.mx||{}).modes||[]).forEach(m=>X[m.mode]=m);
  const labelled=ks.some(k=>X[k]);
  $('#modesh').textContent=`How ${L[S]} loses points, by mode.`;
  const nr=VIEW==='80'?N80:3*NK;
  $('#modesnote').textContent=(VIEW==='80'?`${subMiss.length} of ${L[S]}'s ${nr} runs at 80 minutes scored below full marks, on ${new Set(subMiss.map(r=>r.alias)).size} of ${NT} tasks.`:`With 5 hour reruns, ${subMiss.length} of ${L[S]}'s ${nr} runs on the ${NK} kept tasks scored below full marks, on ${new Set(subMiss.map(r=>r.alias)).size} tasks.`)+' Each carries one primary mode.'+(labelled?'':' The modes come from run measures (steps, turn sizes, re-check phrases, where the first delivery sits); no reader has labelled these runs yet (README step 9).');
  $('#modelist').innerHTML=ks.map(k=>{const x=X[k]||{};const n=c[k].length;const ex=x.explain||D.mode_defs[k]||'';
    return `<div class="modeblock"><h3>${esc(k.replace('4800 s limit','80 minute limit'))}<span class="num">${n} of ${subMiss.length} runs</span></h3>
    <div class="track" style="max-width:640px"><span class="fill" style="width:${100*n/subMiss.length}%;background:var(--accent)"></span></div>
    ${ex?`<p>${esc(ex)}</p>`:''}${x.fix_signal?`<p class="foot"><b>Hypothesis for a fix:</b> ${esc(x.fix_signal)}</p>`:''}
    ${(x.examples||[]).length?'<ul class="tight">'+x.examples.map(e=>`<li><b class="num">${esc(e.key.split('-')[0])}</b> ${esc(T(e.key.split('-')[0]))}: ${esc(e.what)} <button class="link" data-k="${e.key}" data-s="${(e.steps||[])[0]||''}">Open trace</button></li>`).join('')+'</ul>':''}
    <p class="foot">Runs: ${c[k].map(r=>`<button class="link" data-k="${r.key}">${r.alias} run ${r.cell}</button>`).join(', ')}</p></div>`}).join('');
  $('#mf').innerHTML='<option value="">All modes</option>'+(SUBRER?'<option value="__long">5 hour reruns below full marks</option>':'')+ks.map(k=>`<option>${esc(k)}</option>`).join('');
}
function matrix(){
  $('#mxnote').textContent=`Each square is one run, coloured by score; a dark ring marks a run that hit the 80 minute limit${RERUN?'; L marks a 5 hour rerun. With the 5 hour toggle on, faded rows are tasks dropped because a rerun had not finished':''}. Click a square to open its trace. Click a task name to read the full prompt the agents were given (names, email addresses and person ids are masked).`;
  const h=['<thead><tr><th>Task</th>'+M.map(m=>`<th><span class="dot" style="background:${COL[m]}"></span>${esc(L[m])}</th>`).join('')+'</tr></thead><tbody>'];
  D.matrix.forEach(row=>{const dropped=VIEW!=='80'&&!D.keep.includes(row.alias);
    h.push(`<tr style="${dropped?'opacity:.35':''}"><td><details class="ptask"><summary><b class="num">${row.alias}</b> ${esc(row.title)} <span class="foot">${esc(row.cat)}</span></summary><pre class="prompt">${esc((D.prompts||{})[row.alias]||'Prompt not available.')}</pre></details></td>`);
    M.forEach(m=>{h.push('<td><div class="cellrow">'+row.cells[m].map((c,i)=>{let [k,r,to]=c;const lg=(row.long[m]||[])[i];if(VIEW!=='80'&&lg){k=lg[0];r=lg[1];to=false}
      return `<button class="sq${to?' to':''}" style="background:${color(r)}" data-k="${k}" title="${row.alias} ${esc(L[m])} run ${i+1}: ${fmt(r,2)}" aria-label="${row.alias} ${esc(L[m])} run ${i+1}, score ${fmt(r,2)}">${k.endsWith('L')?'L':''}</button>`}).join('')+'</div></td>')});
    h.push('</tr>')});
  $('#mxt').innerHTML=h.join('')+'</tbody>';
  const maj=(row,m)=>row.cells[m].map((x,i)=>{const lg=(row.long[m]||[])[i];return VIEW!=='80'&&lg?lg[1]:x[1]}).filter(r=>r>=0.9999).length>=2;
  const rows=D.matrix.filter(r=>VIEW==='80'||D.keep.includes(r.alias));
  $('#h2h').innerHTML=`<thead><tr><th>${rows.length} tasks</th><th>${esc(short(S))} fails, other solves</th><th>${esc(short(S))} solves, other fails</th></tr></thead><tbody>`+OT.map(m=>{let af=0,ap=0;rows.forEach(r=>{const a=maj(r,S),o=maj(r,m);if(!a&&o)af++;if(a&&!o)ap++});return `<tr><td>${esc(L[S])} against ${esc(L[m])}</td><td class="num">${af}</td><td class="num">${ap}</td></tr>`}).join('')+'</tbody>';
}
function cardHtml(r){
  const c=CARDS[r.key]||RCARDS[r.key]||{};
  const oth=OT.map(m=>`${L[m]} ${fmt(taskMean(r.alias,m),2)}`).join(', ');
  return `<details class="card"><summary><b>${r.alias} run ${r.cell}</b><span>${esc(T(r.alias))}</span>${r.timeout?'<span class="chip to">hit 80 min limit</span>':''}${r.view==='long'?'<span class="chip lg">5 hour rerun</span>':''}<span class="chip">score ${fmt(r.reward,2)}</span>${r.chk?`<span class="chip">${r.chk[0]} of ${r.chk[1]} checks passed</span>`:''}<span class="chip">${esc(modeOf(r.key))}</span></summary>
  <div style="display:grid;gap:6px;padding-top:8px;font-size:13.5px"><div class="kv"><span>minutes <b>${fmt(r.minutes,1)}</b></span><span>turns <b>${r.turns}</b></span><span>tool calls <b>${r.tool_calls}</b></span><span>output tokens <b>${fmt(r.out_tok)}</b></span><span>largest turn <b>${fmt(r.max_turn_tokens)}</b></span></div>
  <p>Same task, mean of 3 runs: ${esc(oth)}.</p>${c.grader?`<p><b>Grader:</b> ${esc(c.grader)}</p>`:''}${(c.shows||[]).length?'<ul class="tight">'+c.shows.map(x=>`<li>${esc(x)}</li>`).join('')+'</ul>':''}
  <p><button class="link" data-k="${r.key}">Open the trace</button></p></div></details>`;
}
function drawCards(){
  const f=$('#mf').value;
  let list=f==='__long'?D.runs.filter(r=>r.view==='long'&&r.model===S&&r.reward<0.9999):subMiss.filter(r=>!f||modeOf(r.key)===f);
  list=list.slice().sort((a,b)=>a.key<b.key?-1:1);
  $('#cardsh').textContent=`Every ${L[S]} run below full marks.`;
  $('#clist').innerHTML=`<p class="foot">${list.length} runs</p>`+list.map(cardHtml).join('');
}
$('#mf').onchange=drawCards;
function method(){
  const a=D.V['80'], m=D.meta[S]||{};
  $('#ledger').innerHTML='<thead><tr><th>Set</th><th>Runs or tasks</th></tr></thead><tbody>'+[
    [`Counted runs, ${NM} models x ${NT} tasks x 3`,NM*NT*3],[`${L[S]} runs below full marks at 80 minutes`,subMiss80.length],[`${L[S]} runs that hit the 80 minute limit`,a[S].timeouts],
    ...(RERUN?[['5 hour reruns with a score',sum(RER.map(x=>D.lsum[x].n))],['5 hour reruns without a score at the cutoff',D.pending_keys.length],['Tasks in the 5 hour view',NK]]:[]),
    ...(m.excluded?[['Earlier test runs, excluded',m.excluded]]:[])].map(r=>`<tr><td class="l">${esc(r[0])}</td><td class="num">${r[1]}</td></tr>`).join('')+'</tbody>';
  const pol=[`Harness: Terminus 2 (version 2.0.0) for all ${NM} models, each run in its own sandbox container. It is an agent loop, not a single API call: the model gets the task prompt and a live Linux terminal; each turn it replies in a fixed JSON format (analysis, plan, keystrokes); the harness types the keystrokes, waits the time the model asked for, and returns the screen output. Two tools only: type keystrokes and wait, and mark the task complete. The company systems are tool servers reached by scripts in that terminal.`,
   `Settings: reasoning effort high, internet on, web search off, same prompt and tools for every model. Grading runs after the agent stops.`+(m.setup_note?' '+m.setup_note:''),
   `Counted runs: first 3 finished runs per task and model; ${NM*NT} of ${NM*NT} cells have 3.`,'Full marks: every check passed. Mean score: weighted share of checks passed.','80 minute view: one 4,800 second agent limit for every model.'];
  if(RERUN)pol.push(`5 hour view: only the ${sum(RER.map(x=>D.lsum[x].slots||0))} runs that hit the 80 minute limit (${RER.map(x=>L[x]).join(', ')}) were rerun, at 18,000 seconds. All models are scored on the same tasks: a task whose rerun had not finished is dropped for everyone.`);
  const st=m.attempts;if(st)pol.push(`Provider stalls (the model API sending nothing for 30 minutes) were retried and are not counted as model failures: ${st.stall80} on ${L[S]} runs at 80 minutes${RERUN?' and '+st.stall_long+' in its reruns':''}, from the evaluation lists.`);
  $('#policy').innerHTML=pol.map(x=>`<li>${esc(x)}</li>`).join('');
  $('#notest').innerHTML=['Three runs per task is not a stable rate for one task.','Only high effort was run. Provider latency cannot be separated from model behaviour.',...(RERUN?[`The 5 hour view reruns only the models that timed out (${RER.map(x=>L[x]).join(', ')}); the dropped tasks are where those reruns took longest, so the 5 hour task set favours them. The sensitivity line keeps all ${NT} tasks.`]:[]),(RD.mx?'Failure modes and side-by-side notes are one reader\'s judgement per run, checked against the grader\'s reasons.':'Failure modes here are rule-based labels from run measures. They say how a run went wrong at the level of the clock and the delivery step, not which figure was wrong.')].map(x=>`<li>${esc(x)}</li>`).join('');
  $('#prov').innerHTML=['Run records, timestamps, token counts and grader output pulled read-only from the evaluation platform.',`Rerun state read at ${(D.generated||'').replace('T',' ').replace('Z',' UTC')}.`,'Tasks appear by alias (T01 to T40) and a generic title. No task ids, expected values or names from task data.'].map(x=>`<li>${esc(x)}</li>`).join('');
  const w=WY[S]||{}, l=LT[S]||{}, cap=m.caps;
  const tps=mm=>{const v=D.runs.filter(r=>r.model===mm&&r.view==='80'&&r.agent_min&&r.out_tok).map(r=>r.out_tok/(r.agent_min*60)).sort((x,y)=>y-x);return v.length?v[Math.floor(v.length/2)]:null};
  const rows=[
   ['Is it our harness?',`Same harness (Terminus 2), prompt, tools, sandbox and limits for all ${NM} models.`,`${a[S].timeouts} of ${N80} ${short(S)} runs hit the limit; ${sum(OT.map(x=>a[x].timeouts))} of ${sum(OT.map(x=>a[x].n))} others`],
   ['Is it slow tools or a slow sandbox?','The model asked the terminal to wait for the share of agent time shown; the rest is the model generating.',`${fmt(100*sum(sub80.map(r=>r.wait_s||0))/Math.max(1,sum(sub80.map(r=>r.agent_min*60))),0)}% of agent time waiting`],
   ['Is it a slow endpoint?','Output per second of agent time, median run, set against output per run.',`${fmt(tps(S),1)} tokens per second against ${rng(tps,1)}; ${fmt(a[S].out_tok/1000)}k output tokens per run against ${rng(x=>a[x].out_tok/1000)}k`],
   ...(cap&&cap.turns?[['Did an output cap cut turns off?','Turns of 60,000 or more output tokens, and how many of them returned no text and no command.',`${cap.t60k||0} of ${fmt(cap.turns)} turns reached 60,000 tokens; ${cap.t60k_empty||0} were empty`]]:[]),
   ['Was reasoning effort the same?','All models in this report ran at high reasoning effort.','high for all'],
   ['Does the reply format hurt?','The harness asks for a JSON reply each turn. A reply it cannot read costs a turn.',`${fmt(w.parse_warn_per_run||0,1)} unreadable replies per run against ${rng(x=>(WY[x]||{}).parse_warn_per_run,1)}`],
   ['Is it redoing calls because of the timeout?','A timeout ends the run; nothing is rerun inside it. Steps before the first deliverable show where the steps go.',`${l.steps_query_to_delivery_median} steps from first query to first deliverable against ${rng(x=>(LT[x]||{}).steps_query_to_delivery_median)}`],
   ['Is it failing more calls?','The share of commands whose output contains an error, and the steps spent right after one.',`${fmt(100*(w.error_share||0),0)}% of commands error against ${rng(x=>100*(WY[x]||{}).error_share,0)}%; ${fmt(w.retries_per_run||0)} retry steps per run against ${rng(x=>(WY[x]||{}).retries_per_run)}`],
   ['Provider outages?','Stalls where the API sent nothing for 30 minutes were retried and are not counted as failures.',st?`${st.stall80} at 80 minutes${RERUN?', '+st.stall_long+' in reruns':''}`:'not counted for this model'],
   ...(RERUN?[['Is the 5 hour comparison fair?',`Only ${RER.map(x=>L[x]).join(' and ')} ${RER.length===1?'was':'were'} rerun, and tasks whose rerun had not finished are dropped for every model. Those are the slowest tasks, so this view favours the rerun models. A sensitivity line keeps all ${NT} tasks.`,`${NK} of ${NT} tasks; sensitivity ${D.V.sens0[S].full} of ${D.V.sens0[S].n}`]]:[]),
   ['Could the grader be wrong?',RD.mx?'The grader\'s reasons for each miss were read against the run; where the grader looks stricter than the prompt the run is labelled a grader issue and still counts as not full marks in the totals.':'Not assessed in this report. Where the grader looks stricter than the prompt, a reader pass (README step 9) labels the run a grader issue; it would still count as not full marks in the totals.',RD.mx?`${subMiss80.filter(r=>/stricter/i.test(modeOf(r.key))).length} of ${subMiss80.length} misses`:'n/a']];
  $('#objtab').innerHTML='<thead><tr><th>Question</th><th class="l">Answer</th><th class="l">Number</th></tr></thead><tbody>'+rows.map(r=>`<tr><td class="l"><b>${esc(r[0])}</b></td><td class="l">${esc(r[1])}</td><td class="l num">${esc(r[2])}</td></tr>`).join('')+'</tbody>';
}
function setView(v){VIEW=v;subMiss=v==='80'?subMiss80:subMissLong;$('#v80').setAttribute('aria-pressed',v==='80');$('#vlong').setAttribute('aria-pressed',v!=='80');results();matrix();modes();drawCards()}
$('#v80').onclick=()=>setView('80'); $('#vlong').onclick=()=>setView('long');
if(!SUBRER&&!RERUN)$('#vlong').style.display='none';

// player
const cache={},full={}; let cur=null,curStep=0,FULL=false,MOM=null,ST=[],FD=null;
const sel=$('#pick');
const optText=k=>{const r=runBy[k];return `${r.alias} ${L[r.model]} run ${r.cell}${r.view==='long'?' (5 hour rerun)':''}, score ${fmt(r.reward,2)}`};
function fillPick(){
  const feat=[...new Set(Object.keys(RD.walk||{}).concat(Object.keys(NOTES)))].filter(k=>runBy[k]).sort();
  sel.innerHTML=(feat.length?'<optgroup label="Walked step by step">'+feat.map(k=>`<option value="${k}">${esc(optText(k))}</option>`).join('')+'</optgroup>':'')+`<optgroup label="All ${esc(L[S])} runs below full">`+subMiss80.map(r=>`<option value="${r.key}">${esc(optText(r.key))}</option>`).join('')+'</optgroup>';
}
sel.onchange=()=>open(sel.value,false);
function autoStories(){
  const o=[],add=(r,t)=>{if(r&&!o.some(x=>x[0]===r.key))o.push([r.key,t])};
  add(sub80.slice().sort((a,b)=>b.max_turn_tokens-a.max_turn_tokens)[0],'Largest single turn');
  add(sub80.slice().sort((a,b)=>b.turns-a.turns)[0],'Most turns in one run');
  add(sub80.filter(r=>r.reward>=0.9999).sort((a,b)=>a.turns-b.turns)[0],'Cleanest full-marks run');
  add(sub80.filter(r=>r.reward<0.9999&&!r.timeout).sort((a,b)=>a.reward-b.reward)[0],'Lowest score without a timeout');
  return o}
const STORIES=(RD.stories||autoStories()).filter(x=>runBy[x[0]]);
$('#pltabs').innerHTML=STORIES.map(([k,t])=>`<button data-tab="${k}" aria-pressed="false">${esc(k.split('-')[0])}: ${esc(t)}</button>`).join('');
$('#pltabs').addEventListener('click',e=>{const b=e.target.closest('[data-tab]');if(b)open(b.dataset.tab,false)});
async function getJSON(u){try{const r=await fetch(u);return r.ok?await r.json():null}catch(e){return null}}
async function load(alias){if(!(alias in cache))cache[alias]=await getJSON('data/traces/'+alias+'.json')||{};if(!(alias in full))full[alias]=await getJSON('data/full/'+alias+'.json')||{};return [cache[alias],full[alias]]}
function momentOf(k,steps){
  const t=((RD.sbs||{}).tasks||[]).find(x=>x.argon_key===k||x.peer_key===k);
  if(t){const n=t.argon_key===k?t.diverge_step_argon:t.diverge_step_peer;if(n)return [n,t.why]}
  const W=(RD.walk||{})[k];
  if(W){const ks=Object.keys(W.steps).map(Number).sort((a,b)=>a-b);const pats=[/re-?check|re-?test|again|already (had|settled)|second time|loop/i,/instead|narrow|without|wrong|miss|duplicate|stub|guess|own variant/i,/never|fails|ran out|loses/i];let bad;for(const re of pats){bad=ks.find(n=>re.test(W.steps[n][2]||''));if(bad)break}const any=ks.filter(n=>W.steps[n][2]);const n=bad||any[0];if(n)return [n,W.steps[n][2]]}
  const N=NOTES[k]||{};const nk=Object.keys(N).map(Number).sort((a,b)=>a-b);if(nk.length)return [nk[0],N[nk[0]]];
  if(!steps.length)return null;let big=0;steps.forEach((s,i)=>{if(s[4]>steps[big][4])big=i});return [steps[big][0],`Largest single turn of the run: ${fmt(steps[big][4])} output tokens.`];
}
async function open(k,scroll,step){
  const r=runBy[k];if(!r)return;cur=k;
  if(![...sel.options].some(o=>o.value===k)){const o=document.createElement('option');o.value=k;o.textContent=optText(k);sel.appendChild(o)}
  sel.value=k;document.querySelectorAll('#pltabs button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.tab===k));
  if(scroll)$('#player').scrollIntoView({block:'start'});
  const lf=await load(r.alias);ST=(lf[0]||{})[k]||[];FD=(lf[1]||{})[k]||null;
  MOM=momentOf(k,ST);
  $('#plhead').textContent=`${L[r.model]} / ${r.alias} ${T(r.alias)} / ${r.turns} turns, ${r.tool_calls} tool calls, ${fmt(r.minutes,0)} min / score ${fmt(r.reward,2)}${r.timeout?' / hit the 80 minute limit':''}${r.view==='long'?' / 5 hour rerun':''}`;
  const same=D.runs.filter(x=>x.alias===r.alias&&x.key!==k);
  $('#same').innerHTML='<span class="foot">Same task:</span> '+same.map(x=>`<button data-k="${x.key}">${esc(short(x.model))}${x.view==='long'?' 5h':''} ${x.cell}</button>`).join('');
  $('#pllist').innerHTML=ST.map((s,i)=>`<div data-i="${i}" class="${MOM&&s[0]==MOM[0]?'mom':s[4]>=10000?'long':''}">${String(s[0]).padStart(2,'0')}${DOT}${esc(s[2])}${MOM&&s[0]==MOM[0]?' &#9679;':''}</div>`).join('');
  $('#plslider').max=Math.max(0,ST.length-1);
  try{history.replaceState(null,'','#'+k)}catch(e){}
  let i=0;if(step){const j=ST.findIndex(s=>s[0]==step);if(j>=0)i=j}
  mark(i);
}
function mark(i){
  if(!ST.length){$('#pldetail').innerHTML='<p>No steps recorded.</p>';return}
  curStep=Math.max(0,Math.min(ST.length-1,i));const s=ST[curStep],n=s[0];
  document.querySelectorAll('#pllist div').forEach(e=>e.classList.toggle('on',+e.dataset.i===curStep));
  const el=document.querySelector(`#pllist div[data-i="${curStep}"]`);if(el){const b=$('#pllist');b.scrollTop=el.offsetTop-b.offsetTop-120}
  $('#plslider').value=curStep;$('#plpos').textContent=`step ${n} / ${ST.length}`;
  const f=FD&&FD.find(x=>x[0]===n);const W=((RD.walk||{})[cur]||{}).steps||{};const w=W[n];const note=(NOTES[cur]||{})[n];
  const clip=FULL?'':' clip';
  let h=`<h4>${esc(s[2])}${s[3].length?' <span style="font-size:13px;color:#9fb0c0">'+esc(s[3].join(', '))+'</span>':''}</h4>`;
  if(w)h+=`<div class="pl-walk"><b>${esc(w[0])}</b><br>${esc(w[1])}</div>`;else if(note)h+=`<div class="pl-walk">${esc(note)}</div>`;
  if(f){
    if(f[3])h+=`<div class="pl-lab">Model's reasoning</div><div class="pl-box${clip}">${esc(f[3])}</div>`;
    h+=`<div class="pl-lab">Args</div><div class="pl-box${clip}">${esc((f[4]||[]).map(c=>c[0]+': '+c[1]).join('\n\n')||'(no tool call)')}</div>`;
    h+=`<div class="pl-lab">Result</div><div class="pl-box${clip}">${esc(f[5]||'(no output recorded)')}</div>`;
  }else{h+=`<div class="pl-lab">Args (masked)</div><div class="pl-box${clip}">${esc(s[8]||'(no tool call)')}</div>`}
  h+=`<div class="pl-lab">Meta</div><div class="pl-box">minute ${fmt(s[1],1)}, ${s[5]!=null?s[5]+' s since the previous step, ':''}${fmt(s[4])} output tokens</div>`;
  if(MOM&&n==MOM[0]){const rr=runBy[cur],cf=bestOther(rr.alias);if(rr.model===S&&cf)h+=`<div class="pl-walk">${esc(L[cf.model])} on the same task (its best run): ${cf.turns} turns, ${cf.tool_calls} tool calls, ${fmt(cf.minutes,0)} minutes, score ${fmt(cf.reward,2)}. This run: ${rr.turns} turns, ${rr.tool_calls} tool calls, ${fmt(rr.minutes,0)} minutes, score ${fmt(rr.reward,2)}. <button class="link" data-k="${cf.key}">Open ${esc(short(cf.model))}'s run</button></div>`}
  if(MOM&&n==MOM[0])h+=`<div class="pl-mom">&#9679; WHERE IT GOES WRONG: ${esc(MOM[1]||'')}</div>`;
  $('#pldetail').innerHTML=h;
}
$('#pllist').addEventListener('click',e=>{const d=e.target.closest('[data-i]');if(d)mark(+d.dataset.i)});
$('#plslider').oninput=e=>mark(+e.target.value);
$('#prev').onclick=()=>mark(curStep-1);$('#next').onclick=()=>mark(curStep+1);
$('#plmom').onclick=()=>{if(MOM){const j=ST.findIndex(s=>s[0]==MOM[0]);if(j>=0)mark(j)}};
$('#plfull').onclick=()=>{FULL=!FULL;$('#plfull').textContent='Full detail: '+(FULL?'on':'off');$('#plfull').setAttribute('aria-pressed',FULL);mark(curStep)};
document.addEventListener('keydown',e=>{if(e.target.closest('input,select,textarea'))return;if(e.key==='ArrowRight')mark(curStep+1);if(e.key==='ArrowLeft')mark(curStep-1)});
document.addEventListener('click',e=>{const b=e.target.closest('[data-k]');if(b&&b.dataset.k){e.preventDefault();open(b.dataset.k,true,b.dataset.s?+b.dataset.s:0)}});

// presentation
function hbars(rows,max,fmtv){return '<div class="hb">'+rows.map(([n,v,c])=>`<div class="r"><span>${esc(n)}</span><span class="t"><span class="f" style="width:${Math.max(0.6,100*v/(max||1))}%;background:${c}"></span></span><span class="num">${fmtv(v)}</span></div>`).join('')+'</div>'}
const mrows=f=>M.map(m=>[L[m],f(m),COL[m]]);
function slides(){
  const a=D.V['80'],s=D.V.same,w=WY[S],l=LT[S],Z=[];
  const oto=sum(OT.map(m=>a[m].timeouts)),on=sum(OT.map(m=>a[m].n));
  Z.push(`<div class="kick">Turing CompanyBench</div><h2>${esc(L[S])} on ${NT} realistic company jobs.</h2>
   <p class="lede">${NT} jobs built from real operational data of a fintech and personal finance company (redacted and consented), run three times each by ${esc(M.map(m=>L[m]).join(', '))}, in the same agent harness with the same 80 minute limit.</p>
   <div class="big"><div class="stat"><b>${a[S].full} of ${N80}</b><span>${esc(L[S])} runs with full marks (best other: ${Math.max(...OT.map(m=>a[m].full))})</span></div><div class="stat"><b>${a[S].timeouts} of ${N80}</b><span>runs that hit the 80 minute limit (others: ${oto} of ${on})</span></div><div class="stat"><b>${fmt(a[S].tool_calls/(sum(OT.map(m=>a[m].tool_calls))/OT.length),1)}x</b><span>the average tool calls of the other models</span></div></div>`);
  Z.push(`<div class="kick">The test</div><h2>A tool-use test inside a working company, not a quiz.</h2><ul>
   <li>Each task is an analyst's job: audit a fee, reconcile transfers, trace a failed payment, check a fraud report.</li>
   <li>The agent must find the evidence itself across a database, wiki, team chat, issue tracker, email and support desk, then post a result with exact figures.</li>
   <li>Checks compare each result to figures an expert computed. Full marks means every check passed.</li>
   <li>Same harness for every model (Terminus 2: a live terminal, the model types commands and reads the screen), high reasoning effort, 80 minutes.</li></ul>`);
  Z.push(`<div class="kick">Result at 80 minutes</div><h2>${esc(L[S])} is ${ord(rank(S,m=>a[m].full,1))} of ${NM} on full marks and ${ord(rank(S,m=>a[m].mean,1))} on mean score.</h2><div class="charts">
   <div><h4>Full marks, of ${N80} runs</h4>${hbars(mrows(m=>a[m].full),N80,v=>v+' of '+N80)}</div><div><h4>Mean score</h4>${hbars(mrows(m=>a[m].mean),1,v=>fmt(v,2))}</div></div>
   <p>${a[S].timeouts} of ${esc(L[S])}'s runs ran out of time and ${a[S].zero} scored zero.${SUBRER&&s[S].n?` With up to 5 hours, on the ${NK} of ${NT} tasks whose reruns finished, it reaches ${s[S].full} of ${s[S].n} full marks, against ${esc(OT.map(m=>s[m].full+' for '+L[m]).join(', '))}.`:''}</p>`);
  Z.push(`<div class="kick">Time, tokens and tool calls</div><h2>What a run costs in clock, output and calls.</h2><div class="charts">
   <div><h4>Runs that hit the 80 minute limit</h4>${hbars(mrows(m=>a[m].timeouts),Math.max(1,...M.map(m=>a[m].timeouts)),v=>v+' of '+N80)}</div>
   <div><h4>Output tokens per run</h4>${hbars(mrows(m=>a[m].out_tok),Math.max(...M.map(m=>a[m].out_tok)),v=>fmt(v/1000)+'k')}</div>
   <div><h4>Tool calls per run</h4>${hbars(mrows(m=>a[m].tool_calls),Math.max(...M.map(m=>a[m].tool_calls)),v=>fmt(v))}</div>
   <div><h4>Minutes per run</h4>${hbars(mrows(m=>a[m].minutes),Math.max(...M.map(m=>a[m].minutes)),v=>fmt(v))}</div></div>`);
  if(w&&l)Z.push(`<div class="kick">Where the steps go</div><h2>Exploration before the first deliverable, errors, and re-checks.</h2><div class="charts">
   <div><h4>Steps from first data query to first deliverable (median)</h4>${hbars(mrows(m=>(LT[m]||{}).steps_query_to_delivery_median||0),Math.max(...M.map(m=>(LT[m]||{}).steps_query_to_delivery_median||0)),v=>fmt(v))}</div>
   <div><h4>Commands that return an error, share of steps</h4>${hbars(mrows(m=>(WY[m]||{}).error_share||0),Math.max(0.01,...M.map(m=>(WY[m]||{}).error_share||0)),v=>fmt(100*v,0)+'%')}</div></div>
   <ul><li>${esc(L[S])} spends ${fmt(w.retries_per_run)} steps per run right after an error, against ${esc(rng(m=>(WY[m]||{}).retries_per_run))} for the others.</li>
   <li>About ${fmt(w.parse_warn_per_run,1)} replies per run break the harness's reply format (others ${esc(rng(m=>(WY[m]||{}).parse_warn_per_run,1))}).</li></ul>`);
  if(l)Z.push(`<div class="kick">Long turns and loops</div><h2>Very long single turns, and re-check cycles.</h2><div class="charts">
   <div><h4>Turns of 8,000+ output tokens per run</h4>${hbars(mrows(m=>(LT[m]||{}).long_turns_per_run||0),Math.max(0.01,...M.map(m=>(LT[m]||{}).long_turns_per_run||0)),v=>fmt(v,2))}</div>
   <div><h4>Re-check cycles per run</h4>${hbars(mrows(m=>(LT[m]||{}).cycles_per_run||0),Math.max(0.01,...M.map(m=>(LT[m]||{}).cycles_per_run||0)),v=>fmt(v,2))}</div></div>
   <p>${fmt(100*w.time_share_in_8k_turns,0)}% of ${esc(L[S])}'s clock goes to turns of 8,000 or more output tokens${WY[S+'_timeout']?` (${fmt(100*WY[S+'_timeout'].time_share_in_8k_turns,0)}% in runs that hit the limit)`:''}; for the others it is ${esc(rng(m=>100*(WY[m]||{}).time_share_in_8k_turns,0))}%.${l.long_turns?` Of its ${l.long_turns} long turns, ${(l.long_turn_next_action||{}).deliver||0} lead straight to delivering.`:''}</p>`);
  const lx=ltxHTML();if(lx)Z.push(`<div class="kick">Inside the long turns</div><h2>What a long turn looks like.</h2>${lx}`);
  Z.push(`<div class="kick">Is it the model or our setup?</div><h2>Same harness, same tasks, same limits for every model.</h2><ul>
   <li>${esc(L[S])}: ${a[S].timeouts} of ${N80} runs hit the limit. Others: ${oto} of ${on}.</li>
   <li>Provider stalls (the API sending nothing for 30 minutes) were retried and are not counted as model failures.</li>
   <li>Every number here opens to the run and the step behind it in the full report.</li></ul>`);
  return Z;
}
let SI=0,SL=[];
function showSlide(i){SL=SL.length?SL:slides();SI=Math.max(0,Math.min(SL.length-1,i));$('#slideBox').innerHTML=`<div class="slide">${SL[SI]}</div>`;$('#sPos').textContent=`${SI+1} / ${SL.length}`}
$('#sPrev').onclick=()=>showSlide(SI-1);$('#sNext').onclick=()=>showSlide(SI+1);
function setMode(m){const sl=m==='slides';$('#deck').hidden=!sl;$('#report').hidden=sl;$('#vSlides').setAttribute('aria-pressed',sl);$('#vReport').setAttribute('aria-pressed',!sl)}
$('#vSlides').onclick=()=>setMode('slides');$('#vReport').onclick=()=>setMode('report');
document.addEventListener('keydown',e=>{if($('#deck').hidden||e.target.closest('input,select,textarea'))return;if(e.key==='ArrowRight'||e.key==='PageDown')showSlide(SI+1);if(e.key==='ArrowLeft'||e.key==='PageUp')showSlide(SI-1)});
document.addEventListener('click',e=>{const b=e.target.closest('#slideBox [data-k]');if(b)setMode('report')},true);
function fitBar(){const b=document.querySelector('.modebar');if(b)document.documentElement.style.setProperty('--mbh',b.offsetHeight+'px')}
window.addEventListener('resize',fitBar);fitBar();

(function(){const lx=ltxHTML();if(lx){$('#ltxbox').innerHTML=lx;$('#ltxnote').textContent=`The runs of ${L[S]} that hit the 80 minute limit with the largest single turns, each set against the other models on the same task. Each long turn is listed with what the model did next.`}else $('#ltxwrap').style.display='none'})();
lede();results();timeSection();longpanel();sbs();modes();matrix();drawCards();method();fillPick();showSlide(0);
const h0=(location.hash||'').slice(1);if(runBy[h0])setMode('report');
if(window.__OPEN_REPORT)setMode('report');
open(runBy[h0]?h0:(STORIES[0]||[])[0]||(sel.options[0]||{}).value,false);
