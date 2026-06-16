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
function renderMD(el, text, fallback) {
  el.innerHTML = text ? marked.parse(text) : `<p class="muted">${fallback}</p>`;
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
    table.innerHTML = '<tbody><tr><td class="muted">아직 조기 신호 종목이 없습니다. 며칠 데이터가 쌓이면 막 출몰하는 소형주가 잡힙니다.</td></tr></tbody>';
    return;
  }
  table.innerHTML =
    '<thead><tr><th>🌱 종목</th><th>시장</th><th>연결 성장사업</th><th>첫 등장</th><th>최근활동</th><th>누적</th><th>선점점수</th></tr></thead>' +
    '<tbody>' + rows.map(r =>
      '<tr>' +
      `<td>${r.name}${r.size ? ` <span class="tag">${r.size}</span>` : ''}</td>` +
      `<td><span class="tag">${r.market}</span></td>` +
      `<td class="muted">${r.theme || '—'}</td>` +
      `<td class="muted">${(r.firstSeen || '').slice(5)} <span class="tag">D-${r.ageDays}</span></td>` +
      `<td><span class="delta-up">↗ ${r.last3}</span></td>` +
      `<td>${r.total}</td>` +
      `<td><b>${r.score}</b></td>` +
      '</tr>').join('') + '</tbody>';
}

let sortState = {};
function renderFreqTable(tableId, rows, hasMarket) {
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
  table.innerHTML =
    '<thead><tr>' + cols.map(c => `<th data-k="${c.key}">${c.label}</th>`).join('') + '</tr></thead>' +
    '<tbody>' + (rows.length ? rows.map(r =>
      '<tr>' +
      `<td>${r.name}</td>` +
      (hasMarket ? `<td><span class="tag">${r.market}</span></td>` : '') +
      `<td>${r.today}</td>` +
      `<td>${deltaCell(r.delta)}</td>` +
      `<td>${r.d7}</td>` +
      `<td>${r.d30}</td>` +
      `<td>${r.total}</td>` +
      `<td class="muted">${r.lastSeen.slice(5)}</td>` +
      '</tr>').join('')
      : `<tr><td colspan="${cols.length}" class="muted">아직 데이터가 없습니다. 첫 브리핑이 실행되면 채워집니다.</td></tr>`) +
    '</tbody>';
  table.querySelectorAll('th').forEach(th => th.onclick = () => {
    const k = th.dataset.k;
    if (st.key === k) st.dir *= -1; else { st.key = k; st.dir = -1; }
    renderFreqTable(tableId, rows, hasMarket);
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
  if (!items.length) { list.innerHTML = '<li class="muted">아직 브리핑 없음</li>'; return; }
  list.innerHTML = items.map((b, i) =>
    `<li data-file="${b.file}" data-i="${i}">${b.date} ${b.session === 'AM' ? '오전' : '오후'}</li>`).join('');
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
async function loadCryptoFearGreed() {
  try {
    const r = await fetch('https://api.alternative.me/fng/?limit=1');
    const j = await r.json();
    const d = j.data && j.data[0];
    if (!d) throw 0;
    const v = parseInt(d.value, 10);
    const ko = FG_KO[d.value_classification] || d.value_classification;
    paintGauge('cgfg', v, `${ko} (${v})`, '');
  } catch (e) { paintGauge('cgfg', null, '불러오기 실패'); }
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
    table.innerHTML =
      '<thead><tr><th>코인</th><th>달러</th><th>원화</th><th>24h</th></tr></thead><tbody>' +
      coins.map(([id, name]) => {
        const d = j[id]; if (!d) return '';
        return `<tr><td>${name}</td><td>${usd(d.usd)}</td><td>${won(d.krw)}</td><td>${chg(d.usd_24h_change)}</td></tr>`;
      }).join('') + '</tbody>';
  } catch (e) {
    table.innerHTML = '<tbody><tr><td class="muted">코인 시세를 불러오지 못했습니다(잠시 후 자동 재시도).</td></tr></tbody>';
  }
}
async function loadMarketIndicators() {
  const data = await getJSON(`${DATA}/market-indicators.json`);
  const table = document.getElementById('indexTable');
  if (!data) {
    paintGauge('sfg', null, '다음 브리핑에서 갱신');
    if (table) table.innerHTML = '<tbody><tr><td class="muted">증시 지표는 다음 브리핑(7시·19시)에 생성됩니다.</td></tr></tbody>';
    return;
  }
  const when = data.updatedAt ? new Date(data.updatedAt).toLocaleString('ko-KR') : '';
  // 주식 공포·탐욕
  const sf = data.stock_fng || {};
  paintGauge('sfg', sf.value, sf.value != null ? `${sf.label || ''} (${sf.value})` : '데이터 없음',
             when ? `· ${when}` : '');
  // 증시·매크로 지표 표
  const rows = data.indices || [];
  const idxTime = document.getElementById('idxTime');
  if (idxTime && when) idxTime.textContent = `· 기준 ${when}`;
  if (table) {
    table.innerHTML = rows.length
      ? '<thead><tr><th>지표</th><th>값</th><th>변동</th><th>출처</th></tr></thead><tbody>' +
        rows.map(x => `<tr><td>${x.name || ''}</td><td>${x.value || '—'}</td>` +
          `<td>${x.change ? `<span class="${(x.change+'').startsWith('-') ? 'delta-down' : 'delta-up'}">${x.change}</span>` : '—'}</td>` +
          `<td>${x.source ? `<a href="${x.source}" target="_blank" rel="noopener">link</a>` : '—'}</td></tr>`).join('') + '</tbody>'
      : '<tbody><tr><td class="muted">지표 데이터가 비어 있습니다.</td></tr></tbody>';
  }
}
async function loadMarketTab() {
  await Promise.all([loadCryptoFearGreed(), loadCoinPrices(), loadMarketIndicators()]);
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
  renderMD(document.getElementById('discoveryBody'),
    await getText(`${DATA}/discovery.md`), '성장기업 발굴은 다음 브리핑부터 생성됩니다.');
  renderMD(document.getElementById('leadingBody'),
    await getText(`${DATA}/leading-signals.md`), '선행 신호 분석은 다음 브리핑부터 생성됩니다.');
  renderMD(document.getElementById('reviewBody'),
    await getText(`${DATA}/review.md`), '중간보스 최종 검토는 다음 브리핑부터 생성됩니다.');
  renderMD(document.getElementById('synthBody'),
    await getText(`${DATA}/synthesis-3day.md`), '3일 종합은 며칠간 데이터가 쌓이면 생성됩니다.');

  const kw = await getJSON(`${DATA}/keyword-index.json`) || { keywords: {} };
  const co = await getJSON(`${DATA}/company-index.json`) || { companies: {} };
  const dc = await getJSON(`${DATA}/discovery-index.json`) || { companies: {} };
  const kwRows = buildRows(kw.keywords);
  const coRows = buildRows(co.companies);
  const dcRows = buildRows(dc.companies);
  renderTopChart('kwChart', kwRows, '키워드');
  renderTopChart('coChart', coRows, '회사');
  renderTopChart('dcChart', dcRows, '발굴기업');
  renderFreqTable('kwTable', kwRows, false);
  renderFreqTable('coTable', coRows, true);
  renderEarlyTable('dcEarlyTable', buildEarlyRows(dc.companies));
  renderFreqTable('dcTable', dcRows, true);

  const ld = await getJSON(`${DATA}/leading-index.json`) || { companies: {} };
  const ldRows = buildRows(ld.companies).sort((a, b) => b.total - a.total);
  renderFreqTable('ldTable', ldRows, true);

  const updated = kw.updatedAt || co.updatedAt;
  document.getElementById('updatedAt').textContent =
    updated ? `최종 갱신: ${new Date(updated).toLocaleString('ko-KR')}` : '아직 갱신 없음';

  await loadArchive();

  // 투자지표: 최초 로드 + 코인 실시간 90초 자동 새로고침
  await loadMarketTab();
  setInterval(() => { loadCryptoFearGreed(); loadCoinPrices(); }, 90000);
})();
