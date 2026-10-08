(function () {
  'use strict';
  const data = JSON.parse(document.getElementById('comparison-data').textContent);
  const root = document.getElementById('comparison');
  const overlay = document.getElementById('connectors');
  const panes = [document.getElementById('scroll-0'), document.getElementById('scroll-1')];
  const entries = Array.from(document.querySelectorAll('.diff-entry'));
  const listPane = document.querySelector('.diff-scroll');
  const filter = document.getElementById('diff-filter');
  let selected = null;
  let frame = 0;

  // Python charOps use Unicode code points. Never slice a JavaScript string
  // using these offsets: emoji and non-BMP characters occupy two UTF-16 units.
  function excerpt(alignment, maxLength) {
    const key = alignment.rightText ? 'right' : 'left';
    const points = Array.from(alignment[key + 'Text']);
    const first = alignment.charOps.find(op => op.op !== 'equal' && op[key + 'End'] > op[key + 'Start']);
    const start = first ? Math.max(0, first[key + 'Start'] - 18) : 0;
    const end = Math.min(points.length, start + maxLength);
    return (start ? '…' : '') + points.slice(start, end).join('') + (end < points.length ? '…' : '');
  }
  document.querySelectorAll('[data-preview]').forEach(element => {
    element.textContent = excerpt(data[Number(element.dataset.preview)], 105);
  });

  function visibleEntries() { return entries.filter(entry => !entry.hidden); }
  function bounds(element) { return element.getBoundingClientRect(); }
  function clamp(value, lo, hi) { return Math.max(lo, Math.min(hi, value)); }
  function scrollToBlock(pane, block) {
    const paneRect = bounds(pane);
    const target = pane.scrollTop + bounds(block).top - paneRect.top - 23;
    pane.scrollTop = Math.max(0, target);
  }
  function keepListVisible(entry) {
    const area = bounds(listPane), item = bounds(entry);
    if (item.top < area.top + 12 || item.bottom > area.bottom - 12) {
      listPane.scrollTop += item.top - area.top - 12;
    }
  }
  function updateNavigation() {
    const visible = visibleEntries();
    const position = visible.findIndex(entry => Number(entry.dataset.index) === selected);
    document.getElementById('previous').disabled = !visible.length || position <= 0;
    document.getElementById('next').disabled = !visible.length || position === visible.length - 1;
    document.getElementById('visible-count').textContent = visible.length;
    document.getElementById('filter-empty').hidden = visible.length !== 0 || entries.length === 0;
    document.getElementById('position-label').textContent = position < 0 ? '点击一项，同时定位两侧' : `${position + 1} / ${visible.length} · ${data[selected].id}`;
  }
  function select(index, moveFocus) {
    const entry = entries.find(item => Number(item.dataset.index) === index);
    if (!entry || entry.hidden) return;
    selected = index;
    entries.forEach(item => {
      const active = item === entry;
      item.classList.toggle('active', active);
      const button = item.querySelector('button');
      if (active) button.setAttribute('aria-current', 'true');
      else button.removeAttribute('aria-current');
    });
    root.querySelectorAll('.alignment.active').forEach(item => item.classList.remove('active'));
    ['left', 'right'].forEach((side, sideIndex) => {
      const block = document.getElementById(`a${index}-${side}`);
      block.classList.add('active');
      scrollToBlock(panes[sideIndex], block);
    });
    keepListVisible(entry);
    if (moveFocus) entry.querySelector('button').focus({preventScroll: true});
    document.getElementById('announcement').textContent = `已定位差异 ${data[index].id}，原件和比对件已同步定位。`;
    updateNavigation();
    queueLines();
  }
  function navigate(direction) {
    const visible = visibleEntries();
    if (!visible.length) return;
    const position = visible.findIndex(entry => Number(entry.dataset.index) === selected);
    const next = clamp(position < 0 ? 0 : position + direction, 0, visible.length - 1);
    select(Number(visible[next].dataset.index), true);
  }
  function drawLines() {
    frame = 0;
    const mainRect = bounds(root);
    const paneRects = panes.map(bounds);
    const fragment = document.createDocumentFragment();
    const make = (tag, attributes) => {
      const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
      Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, String(value)));
      return node;
    };
    overlay.setAttribute('viewBox', `0 0 ${mainRect.width} ${mainRect.height}`);
    entries.forEach(entry => {
      const index = Number(entry.dataset.index);
      if (entry.hidden) return;
      const left = bounds(document.getElementById(`a${index}-left`));
      const right = bounds(document.getElementById(`a${index}-right`));
      const visibleLeft = left.bottom > paneRects[0].top && left.top < paneRects[0].bottom;
      const visibleRight = right.bottom > paneRects[1].top && right.top < paneRects[1].bottom;
      if (!(visibleLeft && visibleRight)) return;
      const y1 = clamp(left.top + Math.min(left.height / 2, 58), paneRects[0].top + 7, paneRects[0].bottom - 7) - mainRect.top;
      const y2 = clamp(right.top + Math.min(right.height / 2, 58), paneRects[1].top + 7, paneRects[1].bottom - 7) - mainRect.top;
      const x1 = paneRects[0].right - mainRect.left - 2;
      const x2 = paneRects[1].left - mainRect.left + 2;
      const mid = (x1 + x2) / 2;
      const operation = data[index].operation;
      fragment.appendChild(make('path', {d: `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`, class: `connection ${operation}${index === selected ? ' active' : ''}`, 'data-connection': index}));
      if (index === selected) {
        fragment.appendChild(make('circle', {cx: x1, cy: y1, r: 2.8, class: `connection-dot ${operation}`}));
        fragment.appendChild(make('circle', {cx: x2, cy: y2, r: 2.8, class: `connection-dot ${operation}`}));
      }
    });
    overlay.replaceChildren(fragment);
  }
  function queueLines() {
    if (!frame) frame = requestAnimationFrame(drawLines);
  }
  entries.forEach(entry => entry.querySelector('button').addEventListener('click', () => select(Number(entry.dataset.index), false)));
  document.getElementById('previous').addEventListener('click', () => navigate(-1));
  document.getElementById('next').addEventListener('click', () => navigate(1));
  filter.addEventListener('change', () => {
    entries.forEach(entry => {
      const alignment = data[Number(entry.dataset.index)];
      const value = filter.value;
      entry.hidden = !(value === 'all' || alignment.operation === value || (value === 'pending' && ['pending', 'uncertain'].includes(alignment.semantic)) || (value === 'equivalent' && alignment.semantic === 'equivalent') || (value === 'unresolved' && alignment.unresolved));
    });
    const visible = visibleEntries();
    if (!visible.some(entry => Number(entry.dataset.index) === selected)) {
      selected = null;
      root.querySelectorAll('.active').forEach(item => item.classList.remove('active'));
      entries.forEach(entry => entry.querySelector('button').removeAttribute('aria-current'));
      if (visible.length) select(Number(visible[0].dataset.index), false);
    }
    updateNavigation();
    queueLines();
  });
  document.addEventListener('keydown', event => {
    if (event.altKey && !event.ctrlKey && !event.metaKey && ['ArrowDown', 'ArrowUp'].includes(event.key)) {
      event.preventDefault();
      navigate(event.key === 'ArrowDown' ? 1 : -1);
    }
  });
  panes.forEach(pane => pane.addEventListener('scroll', queueLines, {passive: true}));
  window.addEventListener('resize', queueLines);
  document.addEventListener('toggle', queueLines, true);
  if (typeof ResizeObserver !== 'undefined') {
    const observer = new ResizeObserver(queueLines);
    observer.observe(root);
    document.querySelectorAll('.document-paper').forEach(paper => observer.observe(paper));
  }
  updateNavigation();
  queueLines();
})();
