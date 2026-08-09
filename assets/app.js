const text = (id, value) => {
  const el = document.getElementById(id);
  if (el) el.textContent = value ?? '—';
};

fetch('data/ndx_mom30_latest.json', { cache: 'no-store' })
  .then((response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  })
  .then((data) => {
    text('data-status', data.status === 'ready' ? '已接入真实研究输出' : '等待研究管线输出');
    text('as-of', data.as_of);
    text('ndx-value', data.ndx?.display_value);
    text('mom30-value', data.mom30?.display_value);
    text('research-version', data.research_version);
    text('ndx-note', data.ndx?.note || '等待真实研究输出');
    text('mom30-note', data.mom30?.note || '等待真实研究输出');
  })
  .catch(() => {
    text('data-status', '数据接口暂不可用');
    text('as-of', '—');
  });
