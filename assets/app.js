const text = (id, value) => {
  const el = document.getElementById(id);
  if (el) el.textContent = value ?? '—';
};

const pct = (value) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
};

const renderTop30 = (rows) => {
  const list = document.getElementById('mom30-list');
  if (!list) return;
  list.replaceChildren();

  if (!Array.isArray(rows) || rows.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    empty.textContent = '等待真实排名输出';
    list.appendChild(empty);
    return;
  }

  rows.forEach((row) => {
    const a = document.createElement('a');
    a.className = 'rank-row';
    a.href = row.tradingview_4h_url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.title = `${row.ticker} · 打开 TradingView 4小时图`;

    const rank = document.createElement('span');
    rank.className = `rank-num${row.rank <= 3 ? ` top-${row.rank}` : ''}`;
    rank.textContent = String(row.rank).padStart(2, '0');

    const ticker = document.createElement('strong');
    ticker.className = 'ticker';
    ticker.textContent = row.ticker;

    const ret = document.createElement('span');
    ret.className = `return ${Number(row.return_pct) >= 0 ? 'up' : 'down'}`;
    ret.textContent = pct(row.return_pct);

    const action = document.createElement('span');
    action.className = 'tv-link';
    action.textContent = '4H图 ›';

    a.append(rank, ticker, ret, action);
    list.appendChild(a);
  });
};

fetch('data/ndx_mom30_latest.json', { cache: 'no-store' })
  .then((response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  })
  .then((data) => {
    const ready = data.status === 'ready';
    text('data-status', ready ? '真实数据已更新' : '等待研究管线输出');
    text('as-of', data.as_of);
    text('ndx-value', data.ndx?.display_value);
    text('mom30-value', data.mom30?.display_value);
    text('research-version', data.research_version);
    text('ndx-note', data.ndx?.note || '等待真实研究输出');
    text('mom30-note', data.mom30?.note || '等待真实研究输出');
    text('baseline-date', data.ndx?.baseline_date);
    text('leader', data.mom30?.leader || '—');
    text('leader-return', data.mom30?.leader ? pct(data.mom30?.leader_return_pct) : '—');
    renderTop30(data.top30);
  })
  .catch((error) => {
    console.error(error);
    text('data-status', '数据接口暂不可用');
    text('as-of', '—');
    renderTop30([]);
  });
