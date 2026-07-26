// 나만의 투자 브리핑 대시보드
'use strict';

const DATA = './data';

// ---------- 유틸 ----------
async function getJSON(path) {
  try { const r = await fetch(path, { cache: 'no-store' }); if (!r.ok) throw 0; return await r.json(); }
  catch { return null; }
}
async function getText(path) {
  try { const r = await fetch(path, { cache: 'no-store' }); if (!r.ok) throw 0; return await r.text(); }
  catch { return null; }
}
function setHTML(el, value) {
  if (!el) return;
  el.innerHTML = DOMPurify.sanitize(String(value ?? ''), {
    USE_PROFILES: { html: true },
    ADD_ATTR: ['target'],
  });
}
function renderMD(el, text, fallback) {
  setHTML(el, text ? marked.parse(text) : `<p class="muted">${fallback}</p>`);
}
function sortedDates(daily) { return Object.keys(daily || {}).sort(); }
function sumLast(daily, days) {
  const dates = sortedDates(daily);
  const cutoff = dates.slice(-days);
  return cutoff.reduce((s, d) => s + (daily[d] || 0), 0);
}
// 전일 대비 증감: 가장 최근 날짜 vs 그 직전 날짜
function dayDelta(daily) {
  const dates = sortedDates(daily);
  if (dates.length === 0) return { today: 0, prev: 0, pct: null, abs: 0 };
  const today = daily[dates[dates.length - 1]] || 0;
  const prev = dates.length >= 2 ? (daily[dates[dates.length - 2]] || 0) : 0;
  const abs = today - prev;
  let pct = null;
  if (prev > 0) pct = Math.round((abs / prev) * 100);
  else if (today > 0) pct = 100; // 0 → 신규 등장
  return { today, prev, pct, abs };
}
function deltaCell(d) {
  if (d.abs > 0) return `<span class="delta-up">▲ ${d.abs}${d.pct !== null ? ` (${d.pct}%)` : ''}</span>`;
  if (d.abs < 0) return `<span class="delta-down">▼ ${Math.abs(d.abs)}${d.pct !== null ? ` (${d.pct}%)` : ''}</span>`;
  return `<span class="delta-flat">—</span>`;
}

// ---------- 관심 종목 + 기사 아카이브 ----------
const FAV_KEY = 'myFavCompanies';
function loadFavs() { try { return new Set(JSON.parse(localStorage.getItem(FAV_KEY) || '[]')); } catch { return new Set(); } }
function saveFavs() { try { localStorage.setItem(FAV_KEY, JSON.stringify([...FAVS])); } catch {} }
let FAVS = loadFavs();
let ARCHIVE = { companies: {} };
let DCIDX = { companies: {} }, COIDX = { companies: {} }, LDIDX = { companies: {} };
let VERIF = { cases: [] }, WATCH = { top: [], avoid: [], all: [] };
function isFav(name) { return FAVS.has(name); }
function toggleFav(name) { if (FAVS.has(name)) FAVS.delete(name); else FAVS.add(name); saveFavs(); }

function articlesFor(name) {
  const c = ARCHIVE.companies[name];
  return (c && c.articles) ? c.articles.slice() : [];
}
// 한 종목의 관련 기사 → 언론사별 그룹 HTML
function articlesBySourceHTML(name) {
  const arts = articlesFor(name).sort((a, b) => (b.date || '').localeCompare(a.date || ''));
  if (!arts.length)
    return '<div class="art-empty muted">아직 누적된 관련 기사가 없습니다. 다음 수집(7시·19시)부터 언론사별로 쌓입니다.</div>';
  // 언론사 본사명 기준 그룹("한국경제·증권"·"한국경제·경제" → "한국경제")
  const outlet = s => (s || '기타').split('·')[0].trim();
  const bySrc = {};
  arts.forEach(a => { const o = outlet(a.source); (bySrc[o] = bySrc[o] || []).push(a); });
  const groups = Object.entries(bySrc).sort((a, b) => b[1].length - a[1].length);
  return '<div class="art-groups">' + groups.map(([src, list]) =>
    `<div class="art-group"><div class="art-src">📰 ${src} <span class="muted">${list.length}건</span></div>` +
    '<ul class="art-list">' + list.map(a =>
      `<li><span class="art-date muted">${(a.date || '').slice(5)}</span> ` +
      (a.link ? `<a href="${a.link}" target="_blank" rel="noopener">${a.title}</a>` : a.title) +
      (a.source && a.source.includes('·') ? ` <span class="art-sec muted">${a.source.split('·')[1]}</span>` : '') +
      '</li>').join('') +
    '</ul></div>').join('') + '</div>';
}
// 관심 ☆ 버튼 + 기사 펼치기 토글이 달린 종목명 셀 내용
function companyCell(name, extraTag) {
  return `<button class="star${isFav(name) ? ' on' : ''}" data-fav="${name}" title="관심 추가/해제">${isFav(name) ? '★' : '☆'}</button>` +
         `<span class="dc-toggle" data-art="${name}" title="언론사별 관련 기사 보기">${name}${extraTag || ''} <span class="art-caret">▾</span></span>`;
}
function syncStars(name) {
  document.querySelectorAll('.star').forEach(b => {
    if (b.dataset.fav === name) { b.textContent = isFav(name) ? '★' : '☆'; b.classList.toggle('on', isFav(name)); }
  });
}
// 종목명 셀(별·펼치기) 이벤트 바인딩 — 표 다시 그릴 때마다 호출
function bindCompanyCells(table, colspan) {
  table.querySelectorAll('.star').forEach(b => b.onclick = e => {
    e.stopPropagation();
    toggleFav(b.dataset.fav); syncStars(b.dataset.fav); renderFavTab();
  });
  table.querySelectorAll('.dc-toggle').forEach(t => t.onclick = () => {
    const tr = t.closest('tr');
    const next = tr.nextElementSibling;
    if (next && next.classList.contains('art-row')) { next.remove(); t.classList.remove('open'); return; }
    const art = document.createElement('tr');
    art.className = 'art-row';
    setHTML(art, `<td colspan="${colspan}">${articlesBySourceHTML(t.dataset.art)}</td>`);
    tr.after(art);
    t.classList.add('open');
  });
}
function favMeta(name) {
  const v = DCIDX.companies[name] || COIDX.companies[name] || LDIDX.companies[name];
  if (!v) return '';
  const d = dayDelta(v.daily);
  return `<span class="tag">${v.market || ''}</span> ` +
         `<span class="muted">오늘 ${d.today} · 7일 ${sumLast(v.daily, 7)} · 누적 ${v.count || 0}</span> ${deltaCell(d)}`;
}
// 관심 종목 한 개의 "흐름 요약" 칩들: 주가추이 · 유망도 · 검증판정
function favFlow(name) {
  const chips = [];
  // 1) 주가 흐름(최초 등장 → 현재)
  const ph = (PRICEHIST.companies || {})[name];
  if (ph && ph.changePct != null) {
    const up = ph.changePct >= 0;
    chips.push(`<span class="flow-chip ${up ? 'up' : 'down'}">📈 최초→현재 ${up ? '+' : ''}${ph.changePct}%` +
      (ph.firstPrice && ph.lastPrice ? ` <span class="muted">(${Number(ph.firstPrice).toLocaleString('ko-KR')}→${Number(ph.lastPrice).toLocaleString('ko-KR')})</span>` : '') + `</span>`);
  }
  // 2) 유망도(학습 점수) — 대기 중이면
  const w = (WATCH.all || []).find(x => x.name === name);
  if (w) {
    const cls = w.score >= 5 ? 'hot' : w.score >= 3 ? 'up' : w.score <= -3 ? 'down' : '';
    const label = w.score >= 5 ? '🔥강력' : w.score >= 3 ? '유망' : w.score <= -3 ? '⚠️회피' : '중립';
    chips.push(`<span class="flow-chip ${cls}" title="${w.why}">⭐유망도 ${label} (${w.score >= 0 ? '+' : ''}${w.score})</span>`);
  }
  // 3) 검증 판정 — 검증 완료됐으면
  const vc = (VERIF.cases || []).find(x => x.name === name);
  if (vc) {
    const d3 = (vc.checks || []).find(x => x.horizon === 'D+3');
    if (vc.finalVerdict || d3) {
      const exc = d3 && d3.excessPct != null ? d3.excessPct : (d3 ? d3.changePct : null);
      const vtxt = vc.finalVerdict || (d3 ? d3.verdict : '');
      const cls = vtxt === '적중' ? 'up' : vtxt === '빗나감' ? 'down' : '';
      chips.push(`<span class="flow-chip ${cls}">🎯검증 ${vtxt}${exc != null ? ` (지수대비 ${exc >= 0 ? '+' : ''}${exc}%)` : ''}</span>`);
    } else if (vc.status === 'pending') {
      chips.push(`<span class="flow-chip muted">🎯검증 대기(D+3 도래 전)</span>`);
    }
  }
  return chips.length ? `<div class="flow-row">${chips.join(' ')}</div>` : '';
}
function renderFavTab() {
  const wrap = document.getElementById('favBody');
  if (!wrap) return;
  const names = [...FAVS];
  if (!names.length) {
    setHTML(wrap, '<p class="muted">아직 관심 종목이 없습니다. 🎯 검증 탭의 <b>⭐유망 대기 선별</b>, 또는 🌱 발굴·🏢 회사 표에서 종목 옆 ☆를 눌러 추가하세요. 추가하면 여기서 주가 흐름·검증까지 계속 추적됩니다.</p>');
    return;
  }
  // 유망도 높은 순으로 정렬(강력 → 유망 → 나머지)
  const wscore = n => { const w = (WATCH.all || []).find(x => x.name === n); return w ? w.score : -99; };
  names.sort((a, b) => wscore(b) - wscore(a));
  setHTML(wrap, names.map(n =>
    `<div class="fav-card"><div class="fav-head">` +
    `<button class="star on" data-fav="${n}" title="관심 해제">★</button> <b class="fav-name">${n}</b> ${favMeta(n)}` +
    `</div>${favFlow(n)}${articlesBySourceHTML(n)}</div>`).join(''));
  wrap.querySelectorAll('.star').forEach(b => b.onclick = () => {
    toggleFav(b.dataset.fav); syncStars(b.dataset.fav); renderFavTab();
  });
}

// ---------- 빈도 테이블 + 차트 ----------
function buildRows(map) {
  return Object.entries(map || {}).map(([name, v]) => {
    const d = dayDelta(v.daily);
    return {
      name,
      market: v.market || '',
      total: v.count || 0,
      d7: sumLast(v.daily, 7),
      d30: sumLast(v.daily, 30),
      today: d.today,
      delta: d,
      lastSeen: v.lastSeen || '',
    };
  });
}

// ---------- 조기 신호: "뜨기 전 선점" 점수 ----------
// 철학: 누적이 많이 쌓인 = 이미 떠버린 = 늦음. 누적은 적은데 막 출몰 시작한 종목을 우선.
function daysBetween(a, b) {                  // b - a (일). ISO 'YYYY-MM-DD' 기준
  const da = new Date(a.slice(0, 10)), db = new Date(b.slice(0, 10));
  if (isNaN(da) || isNaN(db)) return 999;
  return Math.round((db - da) / 86400000);
}
function globalLatestDate(map) {             // 데이터 전체의 가장 최신 날짜 = 기준 '오늘'
  let latest = '';
  for (const v of Object.values(map || {}))
    for (const d of Object.keys(v.daily || {})) if (d > latest) latest = d;
  return latest;
}
function earlyScore(v, latest) {
  const daily = v.daily || {};
  const dates = sortedDates(daily);
  if (!dates.length || !latest) return null;
  const total = v.count || 0;
  const last3 = sumLast(daily, 3);                       // 최근 활동(아직 살아있는 신호)
  const firstSeen = (v.firstSeen || dates[0]).slice(0, 10);
  const ageDays = daysBetween(firstSeen, latest);        // 첫 등장 후 경과일(작을수록 새 종목)
  // 조기 = 막 출몰(첫 등장 12일 이내) + 아직 활동 중 + 누적 적음(이미 떠버린 것 제외)
  const isEarly = ageDays <= 12 && last3 > 0 && total <= 6;
  if (!isEarly) return null;
  // 점수: 신선할수록(ageDays 작을수록)↑ · 최근 모멘텀↑ · 누적 작을수록↑
  const score = (13 - ageDays) * 2 + last3 * 3 + (7 - total);
  return { score, total, last3, ageDays, firstSeen };
}
function buildEarlyRows(map) {
  const latest = globalLatestDate(map);
  return Object.entries(map || {}).map(([name, v]) => {
    const e = earlyScore(v, latest);
    if (!e) return null;
    return { name, market: v.market || '', size: v.size || '', theme: v.theme || '',
             total: e.total, last3: e.last3, ageDays: e.ageDays,
             firstSeen: e.firstSeen, score: e.score };
  }).filter(Boolean).sort((a, b) => b.score - a.score);
}
function renderEarlyTable(tableId, rows) {
  const table = document.getElementById(tableId);
  if (!table) return;
  if (!rows.length) {
    setHTML(table, '<tbody><tr><td class="muted">아직 조기 신호 종목이 없습니다. 며칠 데이터가 쌓이면 막 출몰하는 소형주가 잡힙니다.</td></tr></tbody>');
    return;
  }
  setHTML(table,
    '<thead><tr><th>🌱 종목</th><th>시장</th><th>연결 성장사업</th><th>첫 등장</th><th>최근활동</th><th>누적</th><th>선점점수</th></tr></thead>' +
    '<tbody>' + rows.map(r =>
      '<tr>' +
      `<td class="dc-name">${companyCell(r.name, r.size ? ` <span class="tag">${r.size}</span>` : '')}</td>` +
      `<td><span class="tag">${r.market}</span></td>` +
      `<td class="muted">${r.theme || '—'}</td>` +
      `<td class="muted">${(r.firstSeen || '').slice(5)} <span class="tag">D-${r.ageDays}</span></td>` +
      `<td><span class="delta-up">↗ ${r.last3}</span></td>` +
      `<td>${r.total}</td>` +
      `<td><b>${r.score}</b></td>` +
      '</tr>').join('') + '</tbody>');
  bindCompanyCells(table, 7);
}

let sortState = {};
function renderFreqTable(tableId, rows, hasMarket, interactive) {
  const table = document.getElementById(tableId);
  const cols = [
    { key: 'name', label: hasMarket ? '회사' : '키워드' },
    ...(hasMarket ? [{ key: 'market', label: '시장' }] : []),
    { key: 'today', label: '오늘' },
    { key: 'deltaSort', label: '전일대비' },
    { key: 'd7', label: '7일' },
    { key: 'd30', label: '30일' },
    { key: 'total', label: '누적' },
    { key: 'lastSeen', label: '최근' },
  ];
  const st = sortState[tableId] || (sortState[tableId] = { key: 'd7', dir: -1 });
  rows.sort((a, b) => {
    const k = st.key;
    let av = k === 'deltaSort' ? (a.delta.abs) : a[k];
    let bv = k === 'deltaSort' ? (b.delta.abs) : b[k];
    if (typeof av === 'string') return st.dir * av.localeCompare(bv);
    return st.dir * (av - bv);
  });
  setHTML(table,
    '<thead><tr>' + cols.map(c => `<th data-k="${c.key}">${c.label}</th>`).join('') + '</tr></thead>' +
    '<tbody>' + (rows.length ? rows.map(r =>
      '<tr>' +
      (interactive ? `<td class="dc-name">${companyCell(r.name)}</td>` : `<td>${r.name}</td>`) +
      (hasMarket ? `<td><span class="tag">${r.market}</span></td>` : '') +
      `<td>${r.today}</td>` +
      `<td>${deltaCell(r.delta)}</td>` +
      `<td>${r.d7}</td>` +
      `<td>${r.d30}</td>` +
      `<td>${r.total}</td>` +
      `<td class="muted">${r.lastSeen.slice(5)}</td>` +
      '</tr>').join('')
      : `<tr><td colspan="${cols.length}" class="muted">아직 데이터가 없습니다. 첫 브리핑이 실행되면 채워집니다.</td></tr>`) +
    '</tbody>');
  if (interactive) bindCompanyCells(table, cols.length);
  table.querySelectorAll('th').forEach(th => th.onclick = () => {
    const k = th.dataset.k;
    if (st.key === k) st.dir *= -1; else { st.key = k; st.dir = -1; }
    renderFreqTable(tableId, rows, hasMarket, interactive);
  });
}

const charts = {};
function renderTopChart(canvasId, rows, label) {
  const top = [...rows].sort((a, b) => b.d7 - a.d7).slice(0, 10);
  const ctx = document.getElementById(canvasId);
  if (charts[canvasId]) charts[canvasId].destroy();
  charts[canvasId] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: top.map(r => r.name),
      datasets: [{
        label: `${label} (최근 7일 빈도)`,
        data: top.map(r => r.d7),
        backgroundColor: top.map(r => r.delta.abs > 0 ? '#f85149' : r.delta.abs < 0 ? '#3fb950' : '#2f81f7'),
      }],
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#8b949e' } } },
      scales: {
        x: { ticks: { color: '#8b949e' }, grid: { color: '#283041' } },
        y: { ticks: { color: '#e6edf3' }, grid: { display: false } },
      },
    },
  });
}

// ---------- 아카이브 ----------
async function loadArchive() {
  const manifest = await getJSON(`${DATA}/briefings.json`) || { briefings: [] };
  const list = document.getElementById('archiveList');
  const body = document.getElementById('archiveBody');
  const items = (manifest.briefings || []).slice().reverse();
  if (!items.length) { setHTML(list, '<li class="muted">아직 브리핑 없음</li>'); return; }
  setHTML(list, items.map((b, i) =>
    `<li data-file="${b.file}" data-i="${i}">${b.date} ${b.session === 'AM' ? '오전' : '오후'}</li>`).join(''));
  list.querySelectorAll('li').forEach(li => li.onclick = async () => {
    list.querySelectorAll('li').forEach(x => x.classList.remove('active'));
    li.classList.add('active');
    const txt = await getText(`${DATA}/${li.dataset.file}`);
    renderMD(body, txt, '브리핑을 불러오지 못했습니다.');
  });
}

// ---------- 투자지표 (공포·탐욕 / 코인 / 증시) ----------
function fgColor(v) {           // 0=공포(빨강) … 100=탐욕(초록)
  if (v == null) return '#888';
  if (v < 25) return '#e5484d';
  if (v < 45) return '#f5a524';
  if (v <= 55) return '#9aa0a6';
  if (v <= 74) return '#86c34a';
  return '#2faa54';
}
const FG_KO = { 'Extreme Fear': '극단적 공포', 'Fear': '공포', 'Neutral': '중립',
                'Greed': '탐욕', 'Extreme Greed': '극단적 탐욕' };
function paintGauge(prefix, value, label, timeText) {
  const v = (value == null || isNaN(value)) ? null : Math.round(value);
  const numEl = document.getElementById(prefix + 'Value');
  const labEl = document.getElementById(prefix + 'Label');
  const barEl = document.getElementById(prefix + 'Bar');
  const timeEl = document.getElementById(prefix + 'Time');
  const col = fgColor(v);
  if (numEl) { numEl.textContent = v == null ? '—' : v; numEl.style.color = col; }
  if (labEl) labEl.textContent = label || (v == null ? '데이터 없음' : '');
  if (barEl) { barEl.style.width = (v == null ? 0 : v) + '%'; barEl.style.background = col; }
  if (timeEl && timeText) timeEl.textContent = timeText;
}
// 시계열 헬퍼 + 라인차트
function seriesXY(map) { const d = Object.keys(map || {}).sort(); return { dates: d, vals: d.map(k => map[k]) }; }
function lastDelta(map) { const { vals } = seriesXY(map); return vals.length < 2 ? null : Math.round((vals[vals.length-1] - vals[vals.length-2]) * 100) / 100; }
function deltaTxt(d, unit) {
  if (d == null) return '';
  if (d === 0) return ' · 전회 —';
  return ` · 전회 ${d > 0 ? '▲' : '▼'}${Math.abs(d)}${unit || ''}`;
}
function makeLineChart(canvasId, labels, datasets, yOpts) {
  const ctx = document.getElementById(canvasId); if (!ctx) return;
  if (charts[canvasId]) charts[canvasId].destroy();
  charts[canvasId] = new Chart(ctx, {
    type: 'line', data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { intersect: false, mode: 'index' },
      plugins: { legend: { labels: { color: '#8b949e' } } },
      scales: {
        x: { ticks: { color: '#8b949e' }, grid: { color: '#283041' } },
        y: Object.assign({ ticks: { color: '#8b949e' }, grid: { color: '#283041' } }, yOpts || {}),
      },
    },
  });
}

let coinFGSeries = {}, stockFGSeries = {};
async function loadCryptoFearGreed() {
  try {
    const r = await fetch('https://api.alternative.me/fng/?limit=31');
    const j = await r.json();
    const arr = (j.data || []).slice().reverse();   // 오래된→최신
    coinFGSeries = {};
    arr.forEach(d => {
      const dt = new Date(parseInt(d.timestamp, 10) * 1000).toISOString().slice(0, 10);
      coinFGSeries[dt] = parseInt(d.value, 10);
    });
    const last = arr[arr.length - 1];
    const v = parseInt(last.value, 10);
    const ko = FG_KO[last.value_classification] || last.value_classification;
    paintGauge('cgfg', v, `${ko} (${v})${deltaTxt(lastDelta(coinFGSeries))}`, '');
  } catch (e) { coinFGSeries = {}; paintGauge('cgfg', null, '불러오기 실패'); }
}
function renderFGChart() {
  const dates = Array.from(new Set([...Object.keys(coinFGSeries), ...Object.keys(stockFGSeries)])).sort();
  if (!dates.length) return;
  makeLineChart('fgChart', dates.map(d => d.slice(5)), [
    { label: '코인 공포·탐욕', data: dates.map(d => coinFGSeries[d] ?? null), borderColor: '#f5a524', backgroundColor: 'transparent', spanGaps: true, tension: .3, pointRadius: 0 },
    { label: '주식 공포·탐욕', data: dates.map(d => stockFGSeries[d] ?? null), borderColor: '#2f81f7', backgroundColor: 'transparent', spanGaps: true, tension: .3, pointRadius: 3 },
  ], { min: 0, max: 100 });
}
function renderIndexChart(series) {
  const want = ['코스피', '코스닥', '나스닥', 'S&P 500', '원/달러'];
  const keys = want.filter(k => series[k] && Object.keys(series[k]).length);
  const dates = Array.from(new Set(keys.flatMap(k => Object.keys(series[k])))).sort();
  if (!keys.length || !dates.length) { if (charts['idxChart']) charts['idxChart'].destroy(); return; }
  const colors = ['#f85149', '#3fb950', '#2f81f7', '#f5a524', '#a371f7'];
  const ds = keys.map((k, i) => {
    const m = series[k]; const base = m[Object.keys(m).sort()[0]] || 1;
    return { label: k, borderColor: colors[i % colors.length], backgroundColor: 'transparent', spanGaps: true, tension: .3,
             pointRadius: dates.length < 3 ? 4 : 0,
             data: dates.map(d => m[d] != null ? Math.round(m[d] / base * 1000) / 10 : null) };
  });
  makeLineChart('idxChart', dates.map(d => d.slice(5)), ds);
}
const won = n => '₩' + Math.round(n).toLocaleString('ko-KR');
const usd = n => '$' + n.toLocaleString('en-US', { maximumFractionDigits: 2 });
function chg(p) {
  if (p == null) return '<span class="delta-flat">—</span>';
  const c = p >= 0 ? 'delta-up' : 'delta-down';
  const a = p >= 0 ? '▲' : '▼';
  return `<span class="${c}">${a} ${Math.abs(p).toFixed(2)}%</span>`;
}
async function loadCoinPrices() {
  const table = document.getElementById('coinTable');
  const coins = [['bitcoin', '비트코인(BTC)'], ['ethereum', '이더리움(ETH)'],
                 ['solana', '솔라나(SOL)'], ['ripple', '리플(XRP)']];
  try {
    const ids = coins.map(c => c[0]).join(',');
    const r = await fetch(`https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=usd,krw&include_24hr_change=true`);
    const j = await r.json();
    setHTML(table,
      '<thead><tr><th>코인</th><th>달러</th><th>원화</th><th>24h</th></tr></thead><tbody>' +
      coins.map(([id, name]) => {
        const d = j[id]; if (!d) return '';
        return `<tr><td>${name}</td><td>${usd(d.usd)}</td><td>${won(d.krw)}</td><td>${chg(d.usd_24h_change)}</td></tr>`;
      }).join('') + '</tbody>');
  } catch (e) {
    setHTML(table, '<tbody><tr><td class="muted">코인 시세를 불러오지 못했습니다(잠시 후 자동 재시도).</td></tr></tbody>');
  }
}
async function loadMarketIndicators() {
  const data = await getJSON(`${DATA}/market-indicators.json`);
  const hist = await getJSON(`${DATA}/market-history.json`) || { series: {} };
  stockFGSeries = (hist.series && hist.series['주식 공포·탐욕']) || {};
  renderIndexChart(hist.series || {});
  const table = document.getElementById('indexTable');
  if (!data) {
    paintGauge('sfg', null, '다음 브리핑에서 갱신');
    if (table) setHTML(table, '<tbody><tr><td class="muted">증시 지표는 다음 브리핑(7시·19시)에 생성됩니다.</td></tr></tbody>');
    return;
  }
  const when = data.updatedAt ? new Date(data.updatedAt).toLocaleString('ko-KR') : '';
  // 주식 공포·탐욕 (전회 대비 포함)
  const sf = data.stock_fng || {};
  paintGauge('sfg', sf.value, sf.value != null ? `${sf.label || ''} (${sf.value})${deltaTxt(lastDelta(stockFGSeries))}` : '데이터 없음',
             when ? `· ${when}` : '');
  // 증시·매크로 지표 표
  const rows = data.indices || [];
  const idxTime = document.getElementById('idxTime');
  if (idxTime && when) idxTime.textContent = `· 기준 ${when}`;
  if (table) {
    setHTML(table, rows.length
      ? '<thead><tr><th>지표</th><th>값</th><th>변동</th><th>출처</th></tr></thead><tbody>' +
        rows.map(x => `<tr><td>${x.name || ''}</td><td>${x.value || '—'}</td>` +
          `<td>${x.change ? `<span class="${(x.change+'').startsWith('-') ? 'delta-down' : 'delta-up'}">${x.change}</span>` : '—'}</td>` +
          `<td>${x.source ? `<a href="${x.source}" target="_blank" rel="noopener">link</a>` : '—'}</td></tr>`).join('') + '</tbody>'
      : '<tbody><tr><td class="muted">지표 데이터가 비어 있습니다.</td></tr></tbody>');
  }
}
async function loadMacroCompass() {
  const c = await getJSON(`${DATA}/macro-compass.json`);
  const sg = document.getElementById('compassSignal');
  const cc = document.getElementById('compassCards');
  if (!c) { if (sg) setHTML(sg, '<div class="muted">거시 데이터가 쌓이면 나침반이 생성됩니다.</div>'); return; }
  const rg = c.signal?.regime || '중립';
  const cls = rg === '위험선호' ? 'up' : rg === '위험회피' ? 'down' : 'flat';
  const icon = rg === '위험선호' ? '🟢' : rg === '위험회피' ? '🔴' : '🟡';
  if (sg) setHTML(sg, `<div class="macro-head ${cls}">${icon} 통합 신호: <b>${rg}</b> <span class="muted" style="font-weight:400">(tilt ${c.signal?.tilt >= 0 ? '+' : ''}${c.signal?.tilt ?? 0})</span></div>` +
    `<div class="macro-guide">🎯 ${c.signal?.guidance || ''}</div>`);
  const arrow = t => t === '상승' ? '▲' : t === '하락' ? '▼' : t === '둔화' ? '▼' : t === '가속' ? '▲' : '—';
  const card = (title, main, sub) => `<div class="gauge-card"><div class="gauge-title">${title}</div>` +
    `<div class="gauge-num" style="font-size:1.1rem">${main}</div><div class="gauge-label muted">${sub}</div></div>`;
  const r = c.rates || {}, inf = c.inflation || {}, fx = c.fx || {}, gd = c.gold || {};
  if (cc) setHTML(cc,
    card('💵 금리', r.phase || '—', `美10Y ${r.ust10y ?? '—'} ${arrow(r.ust10yTrend)} · 국고3Y ${r.kr3y ?? '—'} · 韓기준 ${r.krBase ?? '—'}`) +
    card('🔥 인플레이션', inf.tracked ? inf.phase : '미기록', inf.tracked ? `美CPI ${inf.usCpi ?? '—'} ${arrow(inf.usCpiTrend)} · 韓 ${inf.krCpi ?? '—'}` : 'CPI 수집되면 표시') +
    card('💱 달러환율', fx.phase || '—', `원/달러 ${fx.usdkrw ?? '—'} ${arrow(fx.usdkrwTrend)} · DXY ${fx.dxy ?? '—'} · ${fx.level || ''}`) +
    card('🥇 금값(안전자산)', gd.tracked ? gd.read : '미기록', gd.tracked ? `${gd.value ?? '—'} ${arrow(gd.trend)} ${gd.changePct != null ? '(' + (gd.changePct >= 0 ? '+' : '') + gd.changePct + '%)' : ''}` : '금값 수집되면 표시'));
}
async function loadMarketTab() {
  await loadMacroCompass();
  await Promise.all([loadCryptoFearGreed(), loadCoinPrices(), loadMarketIndicators()]);
  renderFGChart();
}

// ---------- 매매일지 ----------
const fmtNum = n => (n == null ? '—' : Number(n).toLocaleString('ko-KR'));
function retCell(r) {
  if (r == null) return '—';
  const c = r >= 0 ? 'delta-up' : 'delta-down';
  return `<span class="${c}">${r >= 0 ? '+' : ''}${r}%</span>`;
}
async function loadMockPortfolio() {
  const m = await getJSON(`${DATA}/mock-portfolio-live.json`) || await getJSON(`${DATA}/mock-portfolio.json`);
  const sm = document.getElementById('mockSummary');
  const bw = document.getElementById('mockBuckets');
  const t = document.getElementById('mockTable');
  if (!m || !m.holdings) { if (sm) setHTML(sm, '<div class="muted">모의 포트폴리오가 아직 없습니다.</div>'); return; }
  const won = n => n == null ? '—' : Number(n).toLocaleString('ko-KR') + '원';
  const pct = v => v == null ? '—' : `<span class="${v >= 0 ? 'delta-up' : 'delta-down'}">${v >= 0 ? '+' : ''}${v}%</span>`;
  const tr = m.totalReturnPct, exc = m.excessPct;
  const card = (title, val, color) => `<div class="gauge-card"><div class="gauge-title">${title}</div><div class="gauge-num" style="color:${color}">${val}</div></div>`;
  if (sm) setHTML(sm,
    card('총 수익률', tr == null ? '—' : (tr >= 0 ? '+' : '') + tr + '%', (tr ?? 0) >= 0 ? '#3fb950' : '#f85149') +
    card('코스피 대비', exc == null ? '—' : (exc >= 0 ? '+' : '') + exc + '%p', (exc ?? 0) >= 0 ? '#3fb950' : '#f85149') +
    card('평가액', m.totalNow != null ? Math.round(m.totalNow / 10000) + '만' : '—', '#2f81f7') +
    card('원금', (m.capital / 10000) + '만', '#8b949e'));
  if (bw) setHTML(bw, '<div class="ai-filter">' + Object.entries(m.bucketAgg || {}).map(([k, a]) => {
    const lb = (m.buckets?.[k]?.label) || k;
    return `<span class="niche-chip">${lb} ${pct(a.returnPct)} <span class="muted">(${won(a.value)})</span></span>`;
  }).join('') + (m.cash ? `<span class="niche-chip">💵 현금 <span class="muted">${won(m.cash)}</span></span>` : '') + '</div>');
  if (t) setHTML(t, '<thead><tr><th>버킷</th><th>종목</th><th>수량</th><th>진입가</th><th>현재가</th><th>수익률</th><th>평가손익</th></tr></thead><tbody>' +
    m.holdings.map(h => `<tr><td>${(m.buckets?.[h.bucket]?.label) || h.bucket}</td>` +
      `<td><b>${h.name}</b> <span class="muted">${h.ticker}</span></td><td>${h.shares}</td>` +
      `<td>${won(h.entryPrice)}</td><td>${won(h.price)}</td><td>${pct(h.returnPct)}</td>` +
      `<td>${h.pnl != null ? (h.pnl >= 0 ? '+' : '') + won(h.pnl) : '—'}</td></tr>`).join('') + '</tbody>');
}
async function loadPortfolio() {
  const pf = await getJSON(`${DATA}/portfolio.json`) || { positions: [], stats: {} };
  const st = pf.stats || {};
  const open = pf.positions.filter(p => p.status === 'open');
  const closed = pf.positions.filter(p => p.status === 'closed');

  const cards = [
    ['보유 중', st.openCount ?? open.length, '#2f81f7'],
    ['청산', st.closedCount ?? closed.length, '#8b949e'],
    ['승률', st.winRate == null ? '—' : st.winRate + '%', (st.winRate ?? 0) >= 50 ? '#2faa54' : '#e5484d'],
    ['평균 수익률', st.avgReturnPct == null ? '—' : (st.avgReturnPct >= 0 ? '+' : '') + st.avgReturnPct + '%', (st.avgReturnPct ?? 0) >= 0 ? '#f85149' : '#3fb950'],
  ];
  const statsEl = document.getElementById('pfStats');
  if (statsEl) setHTML(statsEl, cards.map(([t, v, c]) =>
    `<div class="gauge-card"><div class="gauge-title">${t}</div><div class="gauge-num" style="color:${c}">${v}</div></div>`).join(''));

  const openT = document.getElementById('pfOpenTable');
  if (openT) setHTML(openT, open.length
    ? '<thead><tr><th>종목</th><th>매수일</th><th>매수가</th><th>수량</th><th>테마</th><th>매수 사유</th></tr></thead><tbody>' +
      open.map(p => `<tr><td>${p.name}</td><td class="muted">${p.buy.date}</td><td>${fmtNum(p.buy.price)}</td><td>${fmtNum(p.buy.qty)}</td><td class="muted">${p.theme || '—'}</td><td>${p.buy.reason || '—'}${p.buy.source ? ` <a href="${p.buy.source}" target="_blank" rel="noopener">link</a>` : ''}</td></tr>`).join('') + '</tbody>'
    : '<tbody><tr><td class="muted">보유 중인 종목이 없습니다. 채팅으로 "OO 매수"라고 하면 기록됩니다.</td></tr></tbody>');

  const closedT = document.getElementById('pfClosedTable');
  if (closedT) setHTML(closedT, closed.length
    ? '<thead><tr><th>종목</th><th>매수가→매도가</th><th>수익률</th><th>손익</th><th>보유일</th><th>매도 사유</th></tr></thead><tbody>' +
      closed.map(p => {
        const pnl = p.pnl != null ? `<span class="${p.pnl >= 0 ? 'delta-up' : 'delta-down'}">${p.pnl >= 0 ? '+' : ''}${fmtNum(p.pnl)}</span>` : '—';
        return `<tr><td>${p.name}</td><td>${fmtNum(p.buy.price)} → ${fmtNum(p.sell.price)}</td><td>${retCell(p.returnPct)}</td><td>${pnl}</td><td class="muted">${p.heldDays ?? '—'}일</td><td class="muted">${p.sell.reason || '—'}</td></tr>`;
      }).join('') + '</tbody>'
    : '<tbody><tr><td class="muted">청산 완료된 거래가 아직 없습니다.</td></tr></tbody>');

  renderMD(document.getElementById('holdingsBody'),
    await getText(`${DATA}/holdings-analysis.md`), '보유 종목이 없거나 아직 분석 전입니다. 매수 기록 후 다음 브리핑부터 추적 분석이 생성됩니다.');
}

// ---------- 자체 검증(백테스트) ----------
function verdictCell(v) {
  const map = { '적중': 'delta-up', '빗나감': 'delta-down', '중립': 'delta-flat' };
  const icon = { '적중': '🟢', '빗나감': '🔴', '중립': '⚪' };
  return v ? `<span class="${map[v] || 'delta-flat'}">${icon[v] || ''} ${v}</span>` : '<span class="muted">대기</span>';
}
async function loadVerification() {
  const v = await getJSON(`${DATA}/verification.json`) || { cases: [], stats: {} };
  VERIF = v;
  const st = v.stats || {};
  const cards = [
    ['검증 완료', st.verified ?? 0, '#2f81f7'],
    ['적중률', st.hitRate == null ? '—' : st.hitRate + '%', (st.hitRate ?? 0) >= 50 ? '#2faa54' : '#e5484d'],
    ['평균 D+3', st.avgD3ChangePct == null ? '—' : (st.avgD3ChangePct >= 0 ? '+' : '') + st.avgD3ChangePct + '%', (st.avgD3ChangePct ?? 0) >= 0 ? '#f85149' : '#3fb950'],
    ['대기 중', st.pending ?? 0, '#8b949e'],
  ];
  const se = document.getElementById('vfStats');
  if (se) setHTML(se, cards.map(([t, val, c]) =>
    `<div class="gauge-card"><div class="gauge-title">${t}</div><div class="gauge-num" style="color:${c}">${val}</div></div>`).join(''));

  // 최신 flag 순 정렬
  const cases = (v.cases || []).slice().sort((a, b) => (b.flagDate || '').localeCompare(a.flagDate || ''));
  const t = document.getElementById('vfTable');
  if (t) setHTML(t, cases.length
    ? '<thead><tr><th>종목</th><th>유형</th><th>flag일</th><th>flag가</th><th>D+3 변동</th><th>뉴스</th><th>판정</th></tr></thead><tbody>' +
      cases.map(c => {
        const d3 = (c.checks || []).find(x => x.horizon === 'D+3') || (c.checks || [])[c.checks?.length - 1];
        const chg = d3 && d3.changePct != null ? `<span class="${d3.changePct >= 0 ? 'delta-up' : 'delta-down'}">${d3.changePct >= 0 ? '+' : ''}${d3.changePct}%</span>` : '—';
        const nd = d3 ? ({ '+': '📈', '-': '📉', '0': '—' }[d3.newsDelta] || '—') : '—';
        const typeTag = c.type === 'leading' ? '🔮 선행' : '🌱 발굴';
        return `<tr><td>${c.name}</td><td class="muted">${typeTag}</td><td class="muted">${c.flagDate || ''}</td><td>${c.flagPrice != null ? Number(c.flagPrice).toLocaleString('ko-KR') : '—'}</td><td>${chg}</td><td>${nd}</td><td>${verdictCell(c.finalVerdict)}</td></tr>`;
      }).join('') + '</tbody>'
    : '<tbody><tr><td class="muted">아직 검증 사례가 없습니다. 발굴/선행 종목이 flag된 뒤 3일이 지나면 자동 검증됩니다.</td></tr></tbody>');

  renderMD(document.getElementById('verifyBody'),
    await getText(`${DATA}/verification.md`), '검증 리포트는 데이터가 3일 이상 쌓이면 생성됩니다.');

  await renderCrossValidation();
  await renderWatchPriority();
  await renderThemeBoard();
  await renderMissAnalysis();
  await renderPriceHistory();
  renderFavTab();   // 검증·주가·유망도 로드 후 관심 탭의 흐름 정보 갱신
}
async function loadHistoryTab() {
  const ctx = await getJSON(`${DATA}/macro-context.json`);
  const cb = document.getElementById('macroCtx');
  if (cb && ctx && ctx.snapshot) {
    const s = ctx.snapshot;
    const dn = (v, suf = '') => v == null ? '—' : v + suf;
    const chg = v => v == null ? '' : `<span class="${v >= 0 ? 'delta-up' : 'delta-down'}">${v >= 0 ? '+' : ''}${v}%</span>`;
    setHTML(cb, `<div class="macro-head flat">📊 오늘 거시 스냅샷 <span class="muted" style="font-weight:400">(${ctx.asOf || ''})</span></div>` +
      `<div class="macro-metrics">코스피 ${dn(s.kospi)} ${chg(s.kospi1d)} · 코스닥 ${dn(s.kosdaq)} ${chg(s.kosdaq1d)} · VIX ${dn(s.vix)} · 공포탐욕 ${dn(s.fearGreed)} · 원/달러 ${dn(s.usdkrw)} · WTI ${dn(s.wti)} · 美10Y ${dn(s.ust10y)}</div>` +
      (ctx.activeTriggers && ctx.activeTriggers.length ? `<div class="macro-guide">🔔 켜진 트리거: <b>${ctx.activeTriggers.join(' · ')}</b></div>` : ''));
  }
  renderMD(document.getElementById('macroAnalogBody'),
    await getText(`${DATA}/macro-analog.md`), '거시·뉴스가 쌓이면 오늘 상황과 닮은 과거 패턴이 매칭됩니다(다음 브리핑부터).');
  const pat = await getJSON(`${DATA}/macro-patterns.json`);
  const t = document.getElementById('patternTable');
  if (t && pat && pat.patterns) {
    const edgeCell = p => {
      if (p.method !== 'auto') return '<span class="muted">seed(미검증)</span>';
      const e = p.edge ?? 0;
      const badge = p.validated ? '✅' : '▫';
      return `${badge} <b class="${e >= 0.1 ? 'delta-up' : e < 0 ? 'delta-down' : ''}">${e >= 0 ? '+' : ''}${Math.round(e * 100)}%p</b>` +
        `<div class="muted" style="font-size:.75rem">신뢰 ${Math.round((p.confidence ?? 0) * 100)}% vs 기준 ${Math.round((p.baseRate ?? 0) * 100)}%</div>`;
    };
    const rank = p => p.method === 'auto' ? (p.edge ?? -9) : -99;
    const sorted = pat.patterns.slice().sort((a, b) => rank(b) - rank(a));
    setHTML(t, '<thead><tr><th>패턴</th><th>트리거</th><th>과거 사례 → 결과</th><th>표본</th><th>검증 엣지</th></tr></thead><tbody>' +
      sorted.map(p => `<tr class="${p.validated ? 'watch-hot' : ''}"><td><b>${p.name}</b></td><td class="muted">${p.trigger}</td>` +
        `<td class="niche-samps"><div class="niche-samp">${p.precedent}</div><div class="niche-samp muted">→ ${p.outcome}</div></td>` +
        `<td>${p.method === 'auto' ? p.observed + '건' : (p.observed || 0) + '회'}</td><td>${edgeCell(p)}</td></tr>`).join('') + '</tbody>');
  }
  // 📜 역사 위기 플레이북
  const hist = await getJSON(`${DATA}/macro-history-agg.json`);
  const cn = document.getElementById('crisisNow');
  const ct = document.getElementById('crisisTable');
  if (hist && hist.patterns) {
    const now = hist.currentMatch || [];
    const nowLabels = hist.patterns.filter(p => now.includes(p.type)).map(p => p.label);
    if (cn) setHTML(cn, nowLabels.length
      ? `🔔 <b>오늘 닮은 역사 패턴</b>: ${nowLabels.join(' · ')} — 아래 확률·낙폭·회복기간 참고`
      : '오늘은 뚜렷이 닮은 위기 패턴이 없습니다(정상 국면).');
    const rng = r => r ? `${r[0]}~${r[1]}` : '—';
    if (ct) setHTML(ct, '<thead><tr><th>역사 패턴</th><th>반복확률</th><th>평균 낙폭</th><th>회복기간(개월)</th><th>유리 / 불리</th><th>사례</th></tr></thead><tbody>' +
      hist.patterns.map(p => `<tr class="${now.includes(p.type) ? 'watch-hot' : ''}">` +
        `<td><b>${p.label}</b></td>` +
        `<td><b class="delta-up">${p.repeatProbPct}%</b> <span class="muted">(${p.recoveredCount}/${p.n})</span></td>` +
        `<td><span class="delta-down">${p.avgDrawdownPct}%</span></td>` +
        `<td>${rng(p.recoveryRange)}</td>` +
        `<td class="niche-samps"><div class="niche-samp">✅ ${(p.favored || []).join(', ')}</div><div class="niche-samp muted">⚠️ ${(p.hurt || []).join(', ')}</div></td>` +
        `<td class="muted">${(p.examples || []).map(e => e.year + ' ' + e.name).join('<br>')}</td></tr>`).join('') + '</tbody>');
  }
}
async function loadNicheRadar() {
  const r = await getJSON(`${DATA}/niche-radar.json`);
  const meta = document.getElementById('nicheMeta');
  const t = document.getElementById('nicheCompTable');
  if (!r) { if (meta) meta.textContent = '레이더는 원본 뉴스가 며칠 쌓이면 신호를 잡습니다.'; return; }
  const capTxt = c => c == null ? '—' : c >= 10000 ? (c / 10000).toFixed(1) + '조' : c + '억';
  if (meta) setHTML(meta, `추적 종목 <b>${r.trackedCompanies || 0}</b>개 · 오늘 고유 헤드라인 ${r.corpusToday || 0}건 · 관측창 ${r.window || 30}일`);
  const star = n => `<button class="star${isFav(n) ? ' on' : ''}" data-fav="${n}" title="관심 추가/해제">${isFav(n) ? '★' : '☆'}</button>`;
  const comps = r.companies || [];
  if (t) setHTML(t, comps.length
    ? '<thead><tr><th>종목</th><th>시총</th><th>누적</th><th>최근3일</th><th>촉발/위험</th><th>등장일수</th><th>첫등장</th><th>근거 헤드라인</th></tr></thead><tbody>' +
      comps.map(c => {
        const nm = `${c.name}(${c.code})`;
        const samp = (c.samples || []).map(s => `<div class="niche-samp"><span class="muted">${(s.date || '').slice(5)}</span> ${s.title}</div>`).join('') || '<span class="muted">—</span>';
        return `<tr><td>${star(nm)} <b>${c.name}</b> <span class="muted">${c.code}·${c.market || ''}</span></td>` +
          `<td>${capTxt(c.cap)}</td><td>${c.total}</td><td><b class="delta-up">${c.recent}</b></td>` +
          `<td><span class="delta-up">${c.catalystMentions || 0}</span> / <span class="${c.riskMentions ? 'delta-down' : 'muted'}">${c.riskMentions || 0}</span></td>` +
          `<td>${c.activeDays}일</td><td class="muted">${(c.firstSeen || '').slice(5)}</td>` +
          `<td class="niche-samps">${samp}</td></tr>`;
      }).join('') + '</tbody>'
    : '<tbody><tr><td class="muted">최근 반복 언급되는 소형 조사 후보가 잡히면 표시됩니다(뉴스 누적 필요).</td></tr></tbody>');
  if (t) t.querySelectorAll('.star').forEach(b => b.onclick = e => {
    e.stopPropagation(); toggleFav(b.dataset.fav); syncStars(b.dataset.fav); loadNicheRadar(); renderFavTab();
  });
}
async function loadAiGroup() {
  const g = await getJSON(`${DATA}/ai-group-live.json`) || await getJSON(`${DATA}/ai-group.json`);
  const wrap = document.getElementById('aiGroupBody');
  const mb = document.getElementById('aiMacro');
  if (!g || !wrap) return;
  if (mb && g.macro && g.macro.regime) {
    const rg = g.macro.regime, cls = rg === '위험회피' ? 'down' : rg === '위험선호' ? 'up' : 'flat';
    const icon = rg === '위험회피' ? '🔴' : rg === '위험선호' ? '🟢' : '🟡';
    setHTML(mb, `<div class="macro-head ${cls}">${icon} 현재 거시 국면: <b>${rg}</b> <span class="muted" style="font-weight:400">— 장기 비전 그룹이라 단기 국면과 별개로 관찰</span></div>` +
      (g.macroOverview ? `<div class="macro-guide"><b>🌐 거시 흐름:</b> ${g.macroOverview}</div>` : '') +
      (g.macro.guidance ? `<div class="macro-guide">🎯 ${g.macro.guidance}</div>` : ''));
  }
  const star = n => `<button class="star${isFav(n) ? ' on' : ''}" data-fav="${n}" title="관심 추가/해제">${isFav(n) ? '★' : '☆'}</button>`;
  const momTag = m => m === '승세' ? '<span class="mom up">▲승세</span>' : m === '열세' ? '<span class="mom down">▼열세</span>' : '<span class="mom flat">—중립</span>';
  const chgTag = r => { if (r == null || r === '') return ''; const up = !(String(r).startsWith('-')); return `<span class="${up ? 'delta-up' : 'delta-down'}">${up ? '+' : ''}${r}%</span>`; };
  const byCat = {};
  (g.companies || []).forEach(c => { (byCat[c.category] = byCat[c.category] || []).push(c); });
  const cats = (g.categories || []).filter(cat => (byCat[cat.key] || []).length);
  // 테마 필터 칩
  const chips = `<div class="ai-filter"><button class="ai-chip active" data-cat="__all__">전체</button>` +
    cats.map(c => `<button class="ai-chip" data-cat="${c.key}">${c.label.replace(/^[①-⑧]\s*/, '')}</button>`).join('') + '</div>';
  const body = cats.map(cat => {
    const list = byCat[cat.key] || [];
    return `<div class="ai-cat" data-cat="${cat.key}"><div class="ai-cat-head"><span class="ai-cat-label">${cat.label}</span> <span class="ai-cat-layer">${cat.layer}</span></div>` +
      `<div class="ai-cat-why muted">${cat.why}</div>` +
      (cat.macroThesis ? `<div class="ai-macro-thesis">💡 ${cat.macroThesis}</div>` : '') +
      `<div class="table-scroll"><table class="freq ai-table"><thead><tr><th>종목</th><th>현재가</th><th>당일</th><th>추가후</th><th>모멘텀</th><th>비전·투자포인트</th></tr></thead><tbody>` +
      list.map(c => {
        const nm = `${c.name}(${c.ticker})`;
        const price = c.price ? Number(c.price).toLocaleString('ko-KR') : '—';
        const since = c.sinceAddedPct != null ? chgTag(c.sinceAddedPct) : '<span class="muted">신규</span>';
        return `<tr><td>${star(nm)} <b>${c.name}</b> <span class="muted">${c.ticker}</span>` +
          `<div class="ai-role muted">${c.role}</div></td>` +
          `<td>${price}</td><td>${chgTag(c.changeRate)}</td><td>${since}</td>` +
          `<td>${momTag(c.momentum)}</td>` +
          `<td class="ai-thesis"><b>${c.thesis}</b><div class="muted">✅ ${c.essential}</div><div class="ai-risk muted">⚠️ ${c.risk}</div></td></tr>`;
      }).join('') + '</tbody></table></div></div>';
  }).join('');
  setHTML(wrap, chips + body);
  // 필터 동작
  wrap.querySelectorAll('.ai-chip').forEach(ch => ch.onclick = () => {
    const key = ch.dataset.cat;
    wrap.querySelectorAll('.ai-chip').forEach(x => x.classList.toggle('active', x === ch));
    wrap.querySelectorAll('.ai-cat').forEach(sec => {
      sec.style.display = (key === '__all__' || sec.dataset.cat === key) ? '' : 'none';
    });
  });
  wrap.querySelectorAll('.star').forEach(b => b.onclick = e => {
    e.stopPropagation();
    toggleFav(b.dataset.fav); syncStars(b.dataset.fav); loadAiGroup(); renderFavTab();
  });
}
async function renderMissAnalysis() {
  const m = await getJSON(`${DATA}/miss-analysis.json`);
  const box = document.getElementById('macroBox');
  const sum = document.getElementById('missSummary');
  const t = document.getElementById('missTable');
  const rules = document.getElementById('missRules');
  const dev = document.getElementById('missDevelop');
  if (!m) { if (sum) sum.textContent = '검증이 쌓이면 빗나감 원인분석이 생성됩니다.'; return; }
  // 거시 국면 카드
  const rg = m.macro?.regime || '—';
  const rgCls = rg === '위험회피' ? 'down' : rg === '위험선호' ? 'up' : 'flat';
  const rgIcon = rg === '위험회피' ? '🔴' : rg === '위험선호' ? '🟢' : '🟡';
  if (box) setHTML(box, m.macro ? `<div class="macro-head ${rgCls}">${rgIcon} 현재 거시 국면: <b>${rg}</b></div>` +
    `<div class="macro-metrics muted">코스피 5일 ${m.macro.kospi5d >= 0 ? '+' : ''}${m.macro.kospi5d ?? '—'}% · 공포탐욕 ${m.macro.fearGreed ?? '—'} · VIX ${m.macro.vix ?? '—'}</div>` +
    `<div class="macro-guide">🎯 ${m.macro.guidance || ''}</div>` : '');
  const s = m.summary || {};
  if (sum) setHTML(sum, `검증 ${s.resolved}건 중 <b>빗나감 ${s.miss}건(${s.missRate}%)</b> · ` +
    `그중 <b class="delta-down">${s.preventableShare}%가 예방 가능</b>(약신호·열세테마·후발) → 아래 필터로 자동 차단`);
  if (t) setHTML(t, (m.byCause || []).length
    ? '<thead><tr><th>원인</th><th>건수</th><th>비중</th><th>평균 초과수익</th><th>예방</th></tr></thead><tbody>' +
      m.byCause.map(c => `<tr><td>${c.label}</td><td>${c.n}</td><td>${c.share}%</td>` +
        `<td><span class="delta-down">${c.avgExcess != null ? c.avgExcess + '%' : '—'}</span></td>` +
        `<td style="text-align:center">${c.preventable ? '✅ 필터' : '—'}</td></tr>`).join('') + '</tbody>'
    : '<tbody><tr><td class="muted">빗나감 사례 없음</td></tr></tbody>');
  const rl = m.learnedFilter?.rules || [];
  if (rules) setHTML(rules, rl.length
    ? '<div class="miss-rules-title">🤖 스스로 도출한 필터 규칙 (매 회차 갱신)</div><ul>' +
      rl.map(r => `<li>${r}</li>`).join('') + '</ul>'
    : '');
  if (dev) dev.textContent = m.develop ? `📈 자기발전: ${m.develop}` : '';
}
async function renderCrossValidation() {
  const cv = await getJSON(`${DATA}/cross-signal.json`);
  const tw = document.getElementById('crossTiers');
  const t = document.getElementById('crossTable');
  if (!cv) { if (tw) setHTML(tw, '<div class="muted">데이터가 쌓이면 교차검증 성적이 생성됩니다.</div>'); return; }
  const ts = cv.tierStats || {};
  const base = cv.baseHitRate;
  const card = (label, s, color) => `<div class="gauge-card"><div class="gauge-title">${label}</div>` +
    `<div class="gauge-num" style="color:${color}">${s && s.hitRate != null ? s.hitRate + '%' : '—'}</div>` +
    `<div class="gauge-label muted">n=${s ? s.n : 0}${base != null ? ' · 기준 ' + base + '%' : ''}</div></div>`;
  if (tw) setHTML(tw,
    card('🔥 高수렴(신호 여럿)', ts.high, '#3fb950') +
    card('中수렴', ts.mid, '#f5a524') +
    card('低수렴(신호 1개↓)', ts.low, '#8b949e'));
  // 전향적 추적(우리가 미리 찍은 예측의 실제 성적)
  const pmeta = document.getElementById('crossProspective');
  if (pmeta) {
    const tp = cv.tierProspective || {}, tot = cv.prospectiveTotal || 0;
    if (tot > 0) {
      const h = tp.high || {}, m = tp.mid || {}, l = tp.low || {};
      setHTML(pmeta, `🔮 <b>전향적 검증</b>(우리가 미리 찍은 예측의 실제 성적, ${tot}건): ` +
        `高 <b class="delta-up">${h.hitRate ?? '—'}%</b>(n=${h.n || 0}) · 中 ${m.hitRate ?? '—'}%(n=${m.n || 0}) · 低 ${l.hitRate ?? '—'}%(n=${l.n || 0}) — 회귀 성적과 일치할수록 방법이 확실해짐`);
    } else {
      setHTML(pmeta, '🔮 <b>전향적 검증</b>: 오늘 찍은 高확률 예측들이 <b>3일 뒤부터</b> 실제로 맞았는지 채워집니다(진짜 폐루프).');
    }
  }
  const star = n => `<button class="star${isFav(n) ? ' on' : ''}" data-fav="${n}" title="관심 추가/해제">${isFav(n) ? '★' : '☆'}</button>`;
  const typeTag = t => t === 'leading' ? '🔮선행' : t === 'discovery' ? '🌱발굴' : t;
  const chip = s => { const bad = s.startsWith('⚠️'); return `<span class="flow-chip ${bad ? 'down' : 'up'}">${s}</span>`; };
  const top = (cv.topCandidates || []).filter(c => c.score >= 3);
  if (t) setHTML(t, top.length
    ? '<thead><tr><th>종목</th><th>유형</th><th>수렴점수</th><th>겹친 신호</th></tr></thead><tbody>' +
      top.map(c => `<tr class="${c.score >= 5 ? 'watch-hot' : ''}"><td>${star(c.name)} <b>${c.name}</b>` +
        `${c.score >= 5 ? ' <span class="hot-badge">🔥高확률</span>' : ''}</td>` +
        `<td>${typeTag(c.type)}</td><td><b>${c.score >= 0 ? '+' : ''}${c.score}</b></td>` +
        `<td>${(c.signals || []).map(chip).join(' ')}</td></tr>`).join('') + '</tbody>'
    : '<tbody><tr><td class="muted">수렴 신호가 충분한 대기 후보가 아직 없습니다.</td></tr></tbody>');
  if (t) t.querySelectorAll('.star').forEach(b => b.onclick = e => {
    e.stopPropagation(); toggleFav(b.dataset.fav); syncStars(b.dataset.fav); renderCrossValidation(); renderFavTab();
  });
}
async function renderWatchPriority() {
  const w = await getJSON(`${DATA}/watch-priority.json`) || { top: [], avoid: [], all: [] };
  WATCH = w;
  const typeTag = t => t === 'leading' ? '🔮선행' : t === 'discovery' ? '🌱발굴' : t;
  const starBtn = n => `<button class="star${isFav(n) ? ' on' : ''}" data-fav="${n}" title="관심 추가/해제">${isFav(n) ? '★' : '☆'}</button>`;
  const rowHTML = r => {
    const hot = r.score >= 5;
    return `<tr class="${hot ? 'watch-hot' : ''}">` +
      `<td>${starBtn(r.name)} <b>${r.name}</b>${hot ? ' <span class="hot-badge">🔥주요</span>' : ''}</td>` +
      `<td>${typeTag(r.type)}</td><td>${r.flagDate || ''}</td>` +
      `<td style="text-align:center">${r.concrete ? '✅' : '—'}</td><td class="muted">${r.why}</td></tr>`;
  };
  // 🔥 지금 주목: 최고점(≥5) 종목을 강조 카드로
  const feat = (w.top || []).filter(r => r.score >= 5);
  const fb = document.getElementById('watchFeatured');
  if (fb) setHTML(fb, feat.length
    ? `<div class="feat-title">🔥 지금 주목 — 승세 테마 + 종목 고유 재료를 모두 갖춘 최우선 후보</div>` +
      `<div class="feat-grid">` + feat.map(r =>
        `<div class="feat-card">${starBtn(r.name)} <b>${r.name}</b><div class="feat-sub">${typeTag(r.type)} · ${r.theme}</div>` +
        `<div class="feat-why muted">${r.why}</div></div>`).join('') + `</div>`
    : '');
  const wt = document.getElementById('watchTable');
  if (wt) setHTML(wt, w.top && w.top.length
    ? '<thead><tr><th>종목</th><th>유형</th><th>등재일</th><th>구체재료</th><th>근거</th></tr></thead><tbody>' + w.top.map(rowHTML).join('') + '</tbody>'
    : '<tbody><tr><td class="muted">검증·테마 데이터가 쌓이면 유망 대기 종목이 선별됩니다.</td></tr></tbody>');
  const at = document.getElementById('avoidTable');
  if (at) setHTML(at, (w.avoid && w.avoid.length)
    ? '<thead><tr><th>종목</th><th>유형</th><th>등재일</th><th>사유</th></tr></thead><tbody>' + w.avoid.map(r => `<tr><td>${r.name}</td><td>${typeTag(r.type)}</td><td>${r.flagDate || ''}</td><td class="muted">${r.why}</td></tr>`).join('') + '</tbody>'
    : '<tbody><tr><td class="muted">회피 후보 없음</td></tr></tbody>');
  // 별표 버튼 바인딩(유망표 + 강조카드)
  [fb, wt].forEach(el => el && el.querySelectorAll('.star').forEach(b => b.onclick = e => {
    e.stopPropagation();
    toggleFav(b.dataset.fav); syncStars(b.dataset.fav); renderWatchPriority(); renderFavTab();
  }));
}
async function renderThemeBoard() {
  const sb = await getJSON(`${DATA}/theme-scoreboard.json`) || { themes: [] };
  const t = document.getElementById('themeTable');
  const momTag = m => m === '상승' ? '<span class="delta-up">▲ 승세</span>' : m === '하락' ? '<span class="delta-down">▼ 열세</span>' : '<span class="delta-flat">— 중립</span>';
  if (t) setHTML(t, sb.themes.length
    ? '<thead><tr><th>테마</th><th>모멘텀</th><th>검증</th><th>적중률</th><th>평균 D+3</th></tr></thead><tbody>' +
      sb.themes.map(x => `<tr><td>${x.theme}</td><td>${momTag(x.momentum)}</td><td>${x.n}</td><td>${x.hitRate != null ? x.hitRate + '%' : '—'}</td><td><span class="${(x.avgD3 ?? 0) >= 0 ? 'delta-up' : 'delta-down'}">${x.avgD3 != null ? (x.avgD3 >= 0 ? '+' : '') + x.avgD3 + '%' : '—'}</span></td></tr>`).join('') + '</tbody>'
    : '<tbody><tr><td class="muted">검증 데이터가 쌓이면 테마별 성적이 생성됩니다.</td></tr></tbody>');
  renderMD(document.getElementById('learnBody'),
    await getText(`${DATA}/discovery-learnings.md`), '학습 노트는 검증이 쌓이면 생성됩니다.');
}

let PRICEHIST = { companies: {} };
async function renderPriceHistory() {
  PRICEHIST = await getJSON(`${DATA}/price-history.json`) || { companies: {} };
  const names = Object.keys(PRICEHIST.companies);
  const sel = document.getElementById('priceSelect');
  if (sel) {
    setHTML(sel, '<option value="__all__">📊 전체 비교 (시작=100)</option>' +
      names.map(n => {
        const c = PRICEHIST.companies[n];
        const chg = c.changePct != null ? ` (${c.changePct >= 0 ? '+' : ''}${c.changePct}%)` : '';
        return `<option value="${n}">${n}${chg}</option>`;
      }).join(''));
    sel.onchange = () => drawPriceChart(sel.value);
  }
  drawPriceChart('__all__');
}
function drawPriceChart(which) {
  const comps = PRICEHIST.companies || {};
  const colors = ['#f85149', '#3fb950', '#2f81f7', '#f5a524', '#a371f7', '#e5484d', '#86c34a', '#58a6ff'];
  if (which === '__all__') {
    // 여러 종목 비교 → 시작=100 정규화
    const entries = Object.entries(comps).filter(([, c]) => c.points >= 1);
    if (!entries.length) { if (charts['priceChart']) charts['priceChart'].destroy(); return; }
    const dates = Array.from(new Set(entries.flatMap(([, c]) => Object.keys(c.series)))).sort();
    const ds = entries.slice(0, 8).map(([n, c], i) => {
      const base = c.firstPrice || Object.values(c.series)[0] || 1;
      return { label: n, borderColor: colors[i % colors.length], backgroundColor: 'transparent', spanGaps: true, tension: .3,
               pointRadius: dates.length < 3 ? 4 : 0,
               data: dates.map(d => c.series[d] != null ? Math.round(c.series[d] / base * 1000) / 10 : null) };
    });
    makeLineChart('priceChart', dates.map(d => d.slice(5)), ds);
  } else {
    const c = comps[which]; if (!c) return;
    const dates = Object.keys(c.series).sort();
    makeLineChart('priceChart', dates.map(d => d.slice(5)), [
      { label: `${which} 주가(원)`, borderColor: '#2f81f7', backgroundColor: 'transparent', spanGaps: true, tension: .3,
        pointRadius: dates.length < 3 ? 4 : 2, data: dates.map(d => c.series[d]) },
    ]);
  }
}

// ---------- 탭 ----------
function setupTabs() {
  document.querySelectorAll('.tab').forEach(t => t.onclick = () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById('tab-' + t.dataset.tab).classList.add('active');
  });
}

// ---------- 부트스트랩 ----------
(async function init() {
  setupTabs();

  renderMD(document.getElementById('latestBody'),
    await getText(`${DATA}/latest.md`), '아직 브리핑이 생성되지 않았습니다.');
  renderMD(document.getElementById('analysisBody'),
    await getText(`${DATA}/analysis.md`), '분석·전망(3인 패널)은 다음 브리핑부터 생성됩니다.');
  await loadHistoryTab();
  renderMD(document.getElementById('discoveryBody'),
    await getText(`${DATA}/discovery.md`), '성장기업 발굴은 다음 브리핑부터 생성됩니다.');
  renderMD(document.getElementById('leadingBody'),
    await getText(`${DATA}/leading-signals.md`), '선행 신호 분석은 다음 브리핑부터 생성됩니다.');
  renderMD(document.getElementById('reviewBody'),
    await getText(`${DATA}/review.md`), '중간보스 최종 검토는 다음 브리핑부터 생성됩니다.');
  renderMD(document.getElementById('synthBody'),
    await getText(`${DATA}/synthesis-3day.md`), '3일 종합은 며칠간 데이터가 쌓이면 생성됩니다.');

  ARCHIVE = await getJSON(`${DATA}/article-archive.json`) || { companies: {} };
  const kw = await getJSON(`${DATA}/keyword-index.json`) || { keywords: {} };
  const co = await getJSON(`${DATA}/company-index.json`) || { companies: {} };
  const dc = await getJSON(`${DATA}/discovery-index.json`) || { companies: {} };
  DCIDX = dc; COIDX = co;
  const kwRows = buildRows(kw.keywords);
  const coRows = buildRows(co.companies);
  const dcRows = buildRows(dc.companies);
  renderTopChart('kwChart', kwRows, '키워드');
  renderTopChart('coChart', coRows, '회사');
  renderTopChart('dcChart', dcRows, '발굴기업');
  renderFreqTable('kwTable', kwRows, false);
  renderFreqTable('coTable', coRows, true, true);
  renderEarlyTable('dcEarlyTable', buildEarlyRows(dc.companies));
  renderFreqTable('dcTable', dcRows, true, true);

  const ld = await getJSON(`${DATA}/leading-index.json`) || { companies: {} };
  LDIDX = ld;
  const ldRows = buildRows(ld.companies).sort((a, b) => b.total - a.total);
  renderFreqTable('ldTable', ldRows, true, true);

  renderFavTab();

  const updated = kw.updatedAt || co.updatedAt;
  document.getElementById('updatedAt').textContent =
    updated ? `최종 갱신: ${new Date(updated).toLocaleString('ko-KR')}` : '아직 갱신 없음';

  await loadArchive();
  await loadPortfolio();
  await loadMockPortfolio();
  await loadVerification();
  await loadNicheRadar();
  await loadAiGroup();

  // 투자지표: 최초 로드 + 코인 실시간 90초 자동 새로고침
  await loadMarketTab();
  setInterval(() => { loadCryptoFearGreed(); loadCoinPrices(); }, 90000);
})();
