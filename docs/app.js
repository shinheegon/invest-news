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
  renderFreqTable('dcTable', dcRows, true);

  const updated = kw.updatedAt || co.updatedAt;
  document.getElementById('updatedAt').textContent =
    updated ? `최종 갱신: ${new Date(updated).toLocaleString('ko-KR')}` : '아직 갱신 없음';

  await loadArchive();
})();
