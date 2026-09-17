const state = { data: null };
const $ = id => document.getElementById(id);

function esc(value) {
  return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}
function pct(v){ return `${Number(v || 0).toFixed(1)}%`; }
function severityClass(s){ return String(s || '').toLowerCase(); }
function verdictClass(v){ return String(v || '').toLowerCase(); }

async function checkHealth(){
  try {
    const r = await fetch('/api/health', {cache:'no-store'});
    const j = await r.json();
    if(j.ok){
      $('statusText').textContent = j.youtube_configured ? 'Backend online' : 'Backend online • API key not configured';
      document.querySelector('.backend-status').classList.add('online');
      $('statusDot').style.background = j.youtube_configured ? '#4b7658' : '#a86b4f';
    }
  } catch(e) {
    $('statusText').textContent = 'Backend offline';
    document.querySelector('.backend-status').classList.remove('online');
  }
}

function setLoading(on, text='Collecting YouTube comments and processing public signals…'){
  $('loadingBox').classList.toggle('hidden', !on);
  $('analyzeBtn').disabled = on;
  $('analysisState').textContent = on ? 'RUNNING…' : 'READY';
  $('loadingText').textContent = text;
}
function showError(msg){ $('errorBox').textContent = msg; $('errorBox').classList.remove('hidden'); }
function clearError(){ $('errorBox').classList.add('hidden'); $('errorBox').textContent=''; }

function panel(title, body){
  return `<div class="panel"><div class="panel-head"><b>${title}</b></div><div class="panel-body">${body}</div></div>`;
}

function renderDashboard(d){
  const s = d.sentiment || {};
  const c = d.claims || {};
  const t = d.trend || {};
  const growth = Number(t.growth || 0);
  const dir = t.direction === 'up' ? 'trend-up' : t.direction === 'down' ? 'trend-down' : 'trend-stable';
  const arrow = t.direction === 'up' ? '↑' : t.direction === 'down' ? '↓' : '→';

  $('overviewResults').classList.remove('hidden');
  $('overviewResults').innerHTML = `
    ${panel('Analysis Results', `
      <div class="page-heading"><div><h2 class="results-title">SCHEME: ${esc(d.scheme)}</h2><p class="muted">Generated ${new Date(d.generated_at).toLocaleString()}</p></div><button class="classic-button" id="exportBtn">⇩ Export JSON</button></div>
    `)}
    ${panel('Collection Summary', `<div class="result-grid">
      <div class="kpi"><small>VIDEOS ANALYSED</small><strong>${d.video_count ?? (d.videos||[]).length}</strong></div>
      <div class="kpi"><small>COMMENTS COLLECTED</small><strong>${d.raw ?? 0}</strong></div>
      <div class="kpi"><small>COMMENTS ANALYSED</small><strong>${d.total ?? 0}</strong></div>
      <div class="kpi"><small>FILTERED / SPAM</small><strong>${d.filtered ?? 0}</strong></div>
    </div>`)}
    <div class="subgrid">
      <div>${panel('Public Sentiment', `
        <div class="bar-row"><b>Positive</b><div class="bar-track"><div class="bar-fill positive" style="width:${Number(s.Positive||0)}%"></div></div><span>${pct(s.Positive)}</span></div>
        <div class="bar-row"><b>Neutral</b><div class="bar-track"><div class="bar-fill neutral" style="width:${Number(s.Neutral||0)}%"></div></div><span>${pct(s.Neutral)}</span></div>
        <div class="bar-row"><b>Negative</b><div class="bar-track"><div class="bar-fill negative" style="width:${Number(s.Negative||0)}%"></div></div><span>${pct(s.Negative)}</span></div>
      `)}</div>
      <div>${panel('Trend Snapshot', `<div class="trend-summary"><div class="muted">Complaint volume</div><div class="trend-number ${dir}">${arrow} ${Math.abs(growth).toFixed(1)}%</div><div class="muted">Compared with the earlier available complaint baseline.</div></div>`)}</div>
    </div>
    ${panel('Major Issues', issueTable(d.issues || []))}
    ${panel('Claims Detected', claimsSummary(d.claims || {}, d.claim_rows || []))}
    ${panel('Complaint Trend', trendView(d.trend || {}))}
    ${panel('YouTube Sources', sourceTable(d.videos || []))}
  `;
  $('exportBtn').addEventListener('click', exportJSON);
}

function issueTable(rows){
  if(!rows.length) return '<div class="muted">No recurring issues were detected in the analysed comments.</div>';
  return `<div class="table-wrap"><table class="classic-table"><thead><tr><th>#</th><th>Issue</th><th>Mentions</th><th>Share</th><th>Severity</th></tr></thead><tbody>${rows.map((r,i)=>`<tr><td>${i+1}</td><td>${esc(r.issue)}</td><td>${r.count}</td><td>${pct(r.percentage)}</td><td><span class="badge ${severityClass(r.severity)}">${esc(r.severity)}</span></td></tr>`).join('')}</tbody></table></div>`;
}
function claimsSummary(c, rows){
  const summary = `<div class="result-grid" style="margin-bottom:12px"><div class="kpi"><small>TOTAL CLAIMS</small><strong>${c.total||0}</strong></div><div class="kpi"><small>SUPPORTED</small><strong>${c.supported||0}</strong></div><div class="kpi"><small>CONTRADICTED</small><strong>${c.contradicted||0}</strong></div><div class="kpi"><small>UNVERIFIED</small><strong>${c.unverified||0}</strong></div></div>`;
  if(!rows.length) return summary + '<div class="muted">No claims were extracted from the analysed comments.</div>';
  return summary + `<div class="table-wrap"><table class="classic-table"><thead><tr><th>Claim</th><th>Type</th><th>Verdict</th><th>Evidence / source</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.claim)}</td><td>${esc(r.type)}</td><td><span class="badge ${verdictClass(r.verdict)}">${esc(r.verdict)}</span></td><td>${esc(r.evidence || r.source || '—')}</td></tr>`).join('')}</tbody></table></div>`;
}
function trendView(t){
  const v = t.volume || [];
  if(!v.length) return '<div class="muted">Not enough dated negative comments to construct a complaint-volume trend.</div>';
  const max = Math.max(...v.map(x=>Number(x.count)||0),1);
  return `<div class="trend-card"><div class="chart">${v.map(x=>`<div class="chart-col"><div class="chart-bar" title="${esc(x.date)}: ${x.count}" style="height:${Math.max(2,(Number(x.count)/max)*100)}%"></div><span>${esc(x.date)}</span></div>`).join('')}</div><div class="trend-summary"><div class="muted">Complaint growth</div><div class="trend-number ${t.direction==='up'?'trend-up':t.direction==='down'?'trend-down':'trend-stable'}">${t.direction==='up'?'↑':t.direction==='down'?'↓':'→'} ${Math.abs(Number(t.growth||0)).toFixed(1)}%</div><p class="muted">Daily negative-comment volume derived from comment timestamps.</p></div></div>`;
}
function sourceTable(videos){
  if(!videos.length) return '<div class="muted">No YouTube videos were returned.</div>';
  return `<div class="table-wrap"><table class="classic-table"><thead><tr><th>#</th><th>Video</th><th>Channel</th><th>Published</th><th>Open</th></tr></thead><tbody>${videos.map((v,i)=>`<tr><td>${i+1}</td><td class="source-title">${esc(v.title)}</td><td>${esc(v.channel)}</td><td>${v.published_at ? new Date(v.published_at).toLocaleDateString() : '—'}</td><td><a href="${esc(v.url)}" target="_blank" rel="noopener">YouTube ↗</a></td></tr>`).join('')}</tbody></table></div>`;
}

function renderSections(d){
  $('issues').innerHTML = panel('Major Issues', issueTable(d.issues || []));
  $('claims').innerHTML = panel('Claim Intelligence', claimsSummary(d.claims || {}, d.claim_rows || []));
  $('trends').innerHTML = panel('Complaint Trends', trendView(d.trend || {}));
  $('sources').innerHTML = panel('YouTube Sources', sourceTable(d.videos || []));
}

async function analyse(){
  const scheme = $('schemeInput').value.trim();
  const videos = Number($('videosInput').value);
  const comments = Number($('commentsInput').value);
  if(!scheme){ showError('Enter a government scheme name first.'); return; }
  clearError();
  setLoading(true);
  $('loadingText').textContent = 'Searching YouTube for relevant videos…';
  try{
    $('loadingText').textContent = 'Collecting comments, cleaning text and analysing signals…';
    const r = await fetch('/api/analyze', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({scheme,videos,comments})});
    const j = await r.json();
    if(!r.ok) throw new Error(j.error || 'Analysis failed.');
    state.data = j;
    renderDashboard(j); renderSections(j);
    $('analysisState').textContent = 'COMPLETE';
    document.getElementById('overviewResults').scrollIntoView({behavior:'smooth',block:'start'});
  } catch(e){
    $('analysisState').textContent = 'FAILED';
    showError(e.message || 'Analysis failed.');
  } finally { setLoading(false); }
}

function clearResults(){
  state.data=null; clearError(); $('overviewResults').classList.add('hidden');
  ['issues','claims','trends','sources'].forEach(id => $(id).innerHTML='');
  $('analysisState').textContent='READY';
}
function exportJSON(){
  if(!state.data) return;
  const blob = new Blob([JSON.stringify(state.data,null,2)],{type:'application/json'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`sih_${state.data.scheme.replace(/[^a-z0-9]+/gi,'_').toLowerCase()}_analysis.json`;a.click();URL.revokeObjectURL(a.href);
}
function activate(target){
  const el=$(target); if(el) el.scrollIntoView({behavior:'smooth',block:'start'});
  document.querySelectorAll('[data-target]').forEach(b=>b.classList.toggle('active',b.dataset.target===target));
}
document.querySelectorAll('[data-target]').forEach(b=>b.addEventListener('click',()=>activate(b.dataset.target)));
$('analyzeBtn').addEventListener('click',analyse); $('clearBtn').addEventListener('click',clearResults);
$('schemeInput').addEventListener('keydown',e=>{if(e.key==='Enter') analyse();});
checkHealth(); setInterval(checkHealth,5000);
