let DATA=null, currentFilter='all';
const $=s=>document.querySelector(s), $$=s=>document.querySelectorAll(s);
const pct=x=>x==null?'—':(x*100).toFixed(1)+'%';
const num=x=>x==null?'—':Number(x).toLocaleString('zh-CN',{maximumFractionDigits:1});
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

Promise.all([
 fetch('../site/data/dashboard.json',{cache:'no-store'}).then(r=>r.json()),
 fetch('finance_results.json',{cache:'no-store'}).then(r=>r.json()),
 fetch('finance_history.json',{cache:'no-store'}).then(r=>r.json())
]).then(([dash,fr,fh])=>{
 const asof=dash.meta.data_asof;
 const c50row=dash.enhancement.history.find(x=>x.date===asof) || dash.enhancement.current.concentration;
 const fhMap=new Map(fh.map(x=>[x.date,x.pacc]));
 const cMap=new Map(dash.enhancement.history.map(x=>[x.date,x]));
 const chart=[];
 dash.history.forEach(x=>{
   const f=fhMap.get(x.date), c=cMap.get(x.date);
   if(f==null||!c)return;
   const crowd=Math.max((c.p20_756||0)*100,(c.p20_504||0)*100);
   const cool=(1-f)*100;
   chart.push({date:x.date,score:.5*x.score+.3*crowd+.2*cool,index:x.benchmark_close,bc:x.score,crowding:crowd,fin_cooling:cool});
 });
 const fc=fr.current_financing;
 const crowdNow=Math.max((c50row.p20_756||0)*100,(c50row.p20_504||0)*100);
 const coolNow=(1-fc.pacc)*100;
 DATA={
   meta:{data_asof:asof},
   current:{
     asof,
     display_score:.5*dash.current.score+.3*crowdNow+.2*coolNow,
     bc_score:dash.current.score,bc_status:dash.current.status,
     latest_bc_signal:dash.current.latest_signal,
     c50_share_pct:(c50row.top50_share_pct ?? c50row.top50_share*100),
     c50_p20_756:c50row.p20_756,c50_p20_504:c50row.p20_504,
     fin_balance_yi:fc.balance_yi,fin_20_pct:fc.g20_pct,fin_63_pct:fc.g63_pct,
     fin_accel_bps_day:fc.accel_bps_day,fin_accel_percentile:fc.pacc,fin_cooling_score:coolNow,
     latest_final_signal:{
       date:dash.current.latest_signal?.date||'2026-07-15',
       route:'B路径 → C50确认 → 融资通过',
       bc_path:dash.current.latest_signal?.path||'B',
       bc_score:dash.current.latest_signal?.score||80,
       c50_percentile:dash.enhancement.current.gate.confirmation_percentile,
       fin_accel_percentile:fc.latest_signal_pacc,status:'待验证'
     }
   },
   metrics:fr.metrics,splits:fr.splits,comparisons:fr.comparisons,
   final_signals:fr.final_signals,filtered_by_financing:fr.filtered_by_financing,
   tops:fr.tops,chart,bc_current_paths:dash.current.paths
 };
 renderAll();
}).catch(e=>{
 document.body.insertAdjacentHTML('beforeend','<div style="position:fixed;bottom:10px;left:10px;background:#fff0f0;color:#a22;padding:10px;border:1px solid #eaa;border-radius:8px">数据加载失败：'+esc(e.message)+'</div>')
});

$$('.tab').forEach(b=>b.onclick=()=>{
 $$('.tab').forEach(x=>x.classList.remove('active')); b.classList.add('active');
 $$('.page').forEach(x=>x.classList.remove('active')); $('#page-'+b.dataset.page).classList.add('active');
 location.hash=b.dataset.page;
 if(b.dataset.page==='backtest') setTimeout(drawChart,40);
});
if(location.hash){const k=location.hash.slice(1);const b=$(`.tab[data-page="${k}"]`);if(b)b.click()}

function renderAll(){
 const c=DATA.current;
 $('#asof').textContent='数据截止 '+c.asof+' · 收盘';
 $('#displayScore').textContent=c.display_score.toFixed(1);
 $('#gauge').style.setProperty('--p',c.display_score);
 const high=c.display_score>=80;
 $('#marketState').textContent=high?'顶部风险窗口已开启':'风险观察中';
 $('#marketDesc').textContent=`最新最终候选信号 ${c.latest_final_signal.date}；当前B/C结构分 ${c.bc_score.toFixed(1)}，C50 20日拥挤分位 ${(c.c50_p20_756*100).toFixed(1)}%，融资加速度分位 ${(c.fin_accel_percentile*100).toFixed(1)}%。`;
 $('.riskbar span').style.left=Math.min(99,c.display_score)+'%';
 $('#bcScore').textContent=c.bc_score.toFixed(1);
 $('#c50Score').textContent=(c.c50_p20_756*100).toFixed(1);
 $('#c50Text').textContent=`C50占比 ${c.c50_share_pct.toFixed(2)}%；20日变化756日分位 ${(c.c50_p20_756*100).toFixed(1)}%。`;
 $('#finScore').textContent=c.fin_cooling_score.toFixed(1);
 $('#finText').textContent=`融资余额 ${num(c.fin_balance_yi)}亿元；加速度分位 ${(c.fin_accel_percentile*100).toFixed(1)}%，已明显冷却。`;
 $('#signalDate').textContent=c.latest_final_signal.date;
 $('#signalRoute').textContent=c.latest_final_signal.route;
 $('#signalExplain').textContent=`B路径80分触发；C50确认分位 ${(c.latest_final_signal.c50_percentile*100).toFixed(1)}%；融资加速度分位 ${(c.latest_final_signal.fin_accel_percentile*100).toFixed(1)}% ≤ 75%，当天通过最终确认。`;
 $('#signalStatus').textContent=c.latest_final_signal.status;
 $('#layer1').textContent=`最新B信号 ${c.latest_final_signal.date}`;
 $('#layer2').textContent=`C50 ${(c.latest_final_signal.c50_percentile*100).toFixed(1)}% · 已确认`;
 $('#layer3').textContent=`融资 ${(c.latest_final_signal.fin_accel_percentile*100).toFixed(1)}% · 已通过`;
 renderComponents('bRules',DATA.bc_current_paths.B.components);
 renderComponents('cRules',DATA.bc_current_paths.C.components);
 renderComparison(); renderErrors(); renderSignals(); renderTops(); drawChart();
}
function renderComponents(id,arr){
 $('#'+id).innerHTML=arr.map(x=>`<div class="component"><div><b>${esc(x.name)}</b><small>${esc(x.reading)} · ${esc(x.purpose)}</small></div><div class="component-score">${Number(x.score).toFixed(1)}</div></div>`).join('')
}
function renderComparison(){
 const rows=DATA.comparisons.map((x,i)=>`<tr class="${i===2?'bestrow':''}"><td><b>${esc(x.name)}</b></td><td>${x.signals}</td><td>${x.hits}</td><td>${pct(x.precision)}</td><td>${x.covered}/${x.tops}</td><td>${pct(x.recall)}</td><td>${pct(x.f1)}</td></tr>`).join('');
 $('#compareTable').innerHTML='<thead><tr><th>策略</th><th>成熟信号</th><th>命中</th><th>精确率</th><th>顶部覆盖</th><th>召回率</th><th>F1</th></tr></thead><tbody>'+rows+'</tbody>';
}
function renderErrors(){
 const falses=DATA.final_signals.filter(x=>x.status==='误报');
 $('#falseList').innerHTML=falses.map(x=>`<div class="list-row"><b>${x.signal_date}</b><span>${esc(x.source)}</span></div>`).join('');
 const missed=DATA.tops.filter(x=>x.result==='漏报');
 $('#missedList').innerHTML=missed.map(x=>`<div class="list-row"><b>${x.top_date}</b><span>回撤 ${(x.drawdown*100).toFixed(1)}%</span></div>`).join('');
 $('#filteredList').innerHTML=DATA.filtered_by_financing.map(x=>`<div class="list-row"><b>${x.signal_date}</b><span>${x.original_status} · 融资 ${(x.financing_accel_percentile*100).toFixed(1)}%</span></div>`).join('');
}
function renderSignals(){
 const a=currentFilter==='all'?DATA.final_signals:DATA.final_signals.filter(x=>x.status===currentFilter);
 $('#signalTable').innerHTML='<thead><tr><th>最终信号日</th><th>原候选日</th><th>来源</th><th>融资分位</th><th>结果</th><th>匹配顶部</th><th>提前交易日</th></tr></thead><tbody>'+a.map(x=>`<tr><td><b>${x.signal_date}</b></td><td>${x.original_signal_date}</td><td>${esc(x.source)}</td><td>${pct(x.financing_accel_percentile)}</td><td class="${x.status==='命中'?'hit':'miss'}">${x.status}</td><td>${x.matched_top||'—'}</td><td>${x.lead_trading_days??'—'}</td></tr>`).join('')+'</tbody>';
}
$$('.smallbtn').forEach(b=>b.onclick=()=>{$$('.smallbtn').forEach(x=>x.classList.remove('on'));b.classList.add('on');currentFilter=b.dataset.filter;renderSignals()});
function renderTops(){
 $('#topTable').innerHTML='<thead><tr><th>顶部日期</th><th>确认日期</th><th>后续最大回撤</th><th>覆盖信号</th><th>来源</th><th>提前交易日</th><th>结果</th></tr></thead><tbody>'+DATA.tops.map(x=>`<tr><td><b>${x.top_date}</b></td><td>${x.confirmation_date||'—'}</td><td>${x.drawdown==null?'—':(x.drawdown*100).toFixed(1)+'%'}</td><td>${x.cover_signal||'—'}</td><td>${esc(x.source||'—')}</td><td>${x.lead_trading_days??'—'}</td><td class="${x.result==='命中'?'hit':'miss'}">${x.result}</td></tr>`).join('')+'</tbody>';
}
function drawChart(){
 if(!DATA||!$('#page-backtest').classList.contains('active')) return;
 const cv=$('#backtestChart'), box=cv.parentElement, dpr=window.devicePixelRatio||1;
 const W=box.clientWidth,H=box.clientHeight; cv.width=W*dpr;cv.height=H*dpr;cv.style.width=W+'px';cv.style.height=H+'px';
 const ctx=cv.getContext('2d');ctx.scale(dpr,dpr);ctx.clearRect(0,0,W,H);
 const pad={l:48,r:58,t:18,b:30}, iw=W-pad.l-pad.r, ih=H-pad.t-pad.b, arr=DATA.chart;
 if(!arr.length)return;
 const idxMin=Math.min(...arr.map(x=>x.index)),idxMax=Math.max(...arr.map(x=>x.index)); const ir=idxMax-idxMin||1;
 const x=i=>pad.l+iw*i/(arr.length-1), ys=v=>pad.t+ih*(1-v/100), yi=v=>pad.t+ih*(1-(v-idxMin)/ir);
 ctx.font='10px sans-serif';ctx.fillStyle='#778a9a';ctx.strokeStyle='#e4ebf1';ctx.lineWidth=1;
 [0,20,40,60,80,100].forEach(v=>{const y=ys(v);ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(W-pad.r,y);ctx.stroke();ctx.fillText(v,pad.l-28,y+3)});
 ctx.fillStyle='#c4313e0c';ctx.fillRect(pad.l,ys(100),iw,ys(80)-ys(100));
 ctx.strokeStyle='#c4313e66';ctx.setLineDash([5,4]);ctx.beginPath();ctx.moveTo(pad.l,ys(80));ctx.lineTo(W-pad.r,ys(80));ctx.stroke();ctx.setLineDash([]);
 ctx.strokeStyle='#c4313e';ctx.lineWidth=2;ctx.beginPath();arr.forEach((v,i)=>{const xx=x(i),yy=ys(v.score);i?ctx.lineTo(xx,yy):ctx.moveTo(xx,yy)});ctx.stroke();
 ctx.strokeStyle='#246b9e';ctx.lineWidth=1.6;ctx.beginPath();arr.forEach((v,i)=>{const xx=x(i),yy=yi(v.index);i?ctx.lineTo(xx,yy):ctx.moveTo(xx,yy)});ctx.stroke();
 ctx.fillStyle='#778a9a';[idxMin,(idxMin+idxMax)/2,idxMax].forEach(v=>{const y=yi(v);ctx.fillText(Math.round(v),W-pad.r+8,y+3)});
 const map=new Map(arr.map((v,i)=>[v.date,i]));
 DATA.final_signals.filter(s=>map.has(s.signal_date)).forEach(s=>{const i=map.get(s.signal_date),xx=x(i);ctx.strokeStyle='#d89c1e66';ctx.beginPath();ctx.moveTo(xx,pad.t);ctx.lineTo(xx,H-pad.b);ctx.stroke();ctx.fillStyle='#d89c1e';ctx.beginPath();ctx.arc(xx,ys(arr[i].score),3.2,0,Math.PI*2);ctx.fill()});
 DATA.tops.filter(t=>map.has(t.top_date)).forEach(t=>{const i=map.get(t.top_date),xx=x(i);ctx.fillStyle='#7d315b';ctx.beginPath();ctx.arc(xx,yi(arr[i].index),4,0,Math.PI*2);ctx.fill()});
 ctx.fillStyle='#778a9a';const ticks=5;for(let k=0;k<ticks;k++){const i=Math.round((arr.length-1)*k/(ticks-1));ctx.fillText(arr[i].date.slice(0,7),x(i)-20,H-8)}
 cv.onmousemove=e=>{const rect=cv.getBoundingClientRect(),mx=e.clientX-rect.left;let i=Math.round((mx-pad.l)/iw*(arr.length-1));i=Math.max(0,Math.min(arr.length-1,i));const v=arr[i],tt=$('#tooltip');tt.style.display='block';tt.style.left=Math.min(W-160,Math.max(5,x(i)+10))+'px';tt.style.top=Math.max(5,ys(v.score)-55)+'px';tt.innerHTML=`<b>${v.date}</b><br>综合分 ${v.score.toFixed(1)}<br>中证全指 ${v.index.toFixed(1)}<br>B/C ${v.bc.toFixed(1)} · C50 ${v.crowding.toFixed(1)} · 融资冷却 ${v.fin_cooling.toFixed(1)}`};
 cv.onmouseleave=()=>$('#tooltip').style.display='none';
}
window.addEventListener('resize',()=>{clearTimeout(window.__rt);window.__rt=setTimeout(drawChart,120)});