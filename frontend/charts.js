/*
 * charts.js -- inline SVG charts for the analyst workspace.
 *
 * These draw points the engine already produced. Nothing here computes a business figure: the
 * only arithmetic is the geometry of putting a given value at a given pixel, which is what a
 * chart is. A value that is not in the payload is not on the chart -- there is no interpolation
 * across a missing month, no smoothing, no trend line, and no axis that starts anywhere the
 * data does not.
 *
 * Every chart carries a text summary for a reader who cannot see it, built from the same points.
 */

import { el } from './render.js';

const PAD = { top: 14, right: 14, bottom: 26, left: 14 };

function fmtMoney(n) {
  const v = Number(n);
  if (!isFinite(v)) return '';
  const abs = Math.abs(v);
  if (abs >= 10000000) return '₹' + (v / 10000000).toFixed(2) + ' cr';
  if (abs >= 100000) return '₹' + (v / 100000).toFixed(2) + ' L';
  return '₹' + v.toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

function fmtCount(n) {
  const v = Number(n);
  return isFinite(v) ? v.toLocaleString('en-IN', { maximumFractionDigits: 0 }) : '';
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function monthLabel(period) {
  const m = String(period || '').match(/^(\d{4})-(\d{2})/);
  if (!m) return String(period || '');
  return MONTHS[Number(m[2]) - 1] + ' ' + m[1];
}

function svgEl(name, attrs) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', name);
  Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
  return node;
}

/*
 * A monthly series. `points` is [[period, value], ...] exactly as the engine ordered it.
 *
 * `recentOnly` trims to the last N points for readability. The chart says so beneath itself
 * rather than silently presenting a window as the whole history.
 */
export function lineChart(points, options) {
  const opts = options || {};
  const all = (points || []).filter(function (p) { return isFinite(Number(p[1])); });
  const shown = opts.recent && all.length > opts.recent ? all.slice(-opts.recent) : all;
  const wrap = el('figure', 'chart chart-line');
  wrap.setAttribute('data-chart', 'line');

  if (shown.length < 2) {
    wrap.appendChild(el('figcaption', 'chart-empty',
      'Not enough recorded months to draw a trend.'));
    return wrap;
  }

  const W = 640, H = 180;
  const values = shown.map(function (p) { return Number(p[1]); });
  let lo = Math.min.apply(null, values);
  let hi = Math.max.apply(null, values);
  if (lo === hi) { lo -= 1; hi += 1; }
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const x = function (i) { return PAD.left + (i / (shown.length - 1)) * innerW; };
  const y = function (v) { return PAD.top + innerH - ((v - lo) / (hi - lo)) * innerH; };

  const svg = svgEl('svg', {
    viewBox: '0 0 ' + W + ' ' + H, class: 'chart-svg', role: 'img',
    preserveAspectRatio: 'none',
    'aria-label': (opts.label || 'Monthly trend') + ' from ' + monthLabel(shown[0][0]) +
      ' to ' + monthLabel(shown[shown.length - 1][0]),
  });

  // A zero line where the data crosses it, so a negative month is visibly negative.
  if (lo < 0 && hi > 0) {
    svg.appendChild(svgEl('line', {
      x1: PAD.left, x2: W - PAD.right, y1: y(0), y2: y(0), class: 'chart-zero',
    }));
  }

  const d = shown.map(function (p, i) {
    return (i === 0 ? 'M' : 'L') + x(i).toFixed(1) + ' ' + y(Number(p[1])).toFixed(1);
  }).join(' ');
  svg.appendChild(svgEl('path', { d: d, class: 'chart-path', fill: 'none' }));

  const last = shown.length - 1;
  svg.appendChild(svgEl('circle', {
    cx: x(last).toFixed(1), cy: y(Number(shown[last][1])).toFixed(1), r: 3.5,
    class: 'chart-point',
  }));

  /*
   * One hit target per recorded month. Hovering names the month and prints the engine's own
   * figure for it; clicking asks the page to look at that month, which it does by moving the
   * shared period filter -- the same control the bar uses, so a chart click and a dropdown
   * choice are the same action and cannot disagree.
   */
  const displays = opts.displays || {};
  const selectedIndex = shown.findIndex(function (p) {
    return opts.selected && String(p[0]).slice(0, 7) === String(opts.selected).slice(0, 7);
  });
  const tip = el('p', 'chart-tip');
  tip.setAttribute('role', 'status');
  const step = innerW / Math.max(shown.length - 1, 1);

  shown.forEach(function (point, index) {
    const period = String(point[0]).slice(0, 7);
    const figure = displays[point[0]] || displays[period] || '';
    const label = monthLabel(point[0]) + (figure ? ': ' + figure : '');
    const hit = svgEl('rect', {
      x: (x(index) - step / 2).toFixed(1), y: 0,
      width: Math.max(step, 6).toFixed(1), height: H,
      class: 'chart-hit', 'data-period': period, tabindex: '0', role: 'button',
      'aria-label': 'Show ' + label,
    });
    const show = function () { tip.textContent = label; };
    hit.addEventListener('mouseenter', show);
    hit.addEventListener('focus', show);
    hit.addEventListener('mouseleave', function () { tip.textContent = ''; });
    if (opts.onSelect) {
      const pick = function () { opts.onSelect(period); };
      hit.addEventListener('click', pick);
      hit.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); pick(); }
      });
    }
    svg.appendChild(hit);
    if (index === selectedIndex) {
      svg.appendChild(svgEl('line', {
        x1: x(index).toFixed(1), x2: x(index).toFixed(1), y1: PAD.top,
        y2: (H - PAD.bottom).toFixed(1), class: 'chart-selected-line',
      }));
      svg.appendChild(svgEl('circle', {
        cx: x(index).toFixed(1), cy: y(Number(point[1])).toFixed(1), r: 4.5,
        class: 'chart-selected-point',
      }));
    }
  });
  wrap.appendChild(svg);
  wrap.appendChild(tip);

  const scale = el('div', 'chart-scale');
  scale.appendChild(el('span', 'chart-scale-min', monthLabel(shown[0][0])));
  scale.appendChild(el('span', 'chart-scale-max', monthLabel(shown[last][0])));
  wrap.appendChild(scale);

  const fmt = opts.unit === 'count' ? fmtCount : fmtMoney;
  const caption = el('figcaption', 'chart-caption');
  caption.textContent =
    shown.length + ' recorded months, ' + monthLabel(shown[0][0]) + ' to ' +
    monthLabel(shown[last][0]) + '. Lowest ' + fmt(lo) + ', highest ' + fmt(hi) +
    ', latest ' + fmt(shown[last][1]) + '.' +
    (shown.length < all.length
      ? ' Showing the most recent ' + shown.length + ' of ' + all.length + ' months.'
      : ' This is the whole recorded history.') +
    ' Every point is a recorded month; nothing here is projected.';
  wrap.appendChild(caption);

  // The records stop on the export date, so the month it falls in -- and anything after it --
  // is only recorded as far as that date. The line shows every recorded month, which is what
  // the engine supplied; what it must not do is let the resulting short bar read as a collapse
  // in the business. No month is excluded here and nothing is adjusted: the reason the tail is
  // short is simply stated, in the same words the period comparisons use.
  if (opts.asOf) {
    wrap.appendChild(el('p', 'chart-partial',
      'Records stop on ' + opts.asOf + ', so any month drawn at or after that date is only ' +
      'recorded up to it. A short bar at the end of the line is a part-month, not a fall in ' +
      'the business. Only complete months are compared below.'));
  }
  return wrap;
}

/*
 * Recorded invoiced revenue followed by the engine's projection of it.
 *
 * `history` is [[period, value], ...] of recorded months; `projection` is [{period, value, lower,
 * upper, display, lower_display, upper_display}, ...] exactly as the forecaster produced them.
 * The recorded line is solid, the projected line dashed, the band is the forecaster's own
 * lower/upper for each projected month, and a vertical rule marks where recorded months end.
 * Nothing is estimated here: a projected month with no band draws no band.
 */
export function forecastChart(history, projection, options) {
  const opts = options || {};
  const recorded = (history || []).filter(function (p) { return isFinite(Number(p[1])); });
  const shownHistory = opts.recent && recorded.length > opts.recent
    ? recorded.slice(-opts.recent) : recorded;
  const ahead = (projection || []).filter(function (p) {
    return p && p.value !== null && isFinite(Number(p.value));
  });
  const wrap = el('figure', 'chart chart-line chart-forecast');
  wrap.setAttribute('data-chart', 'forecast');

  if (shownHistory.length < 1 || ahead.length < 1) {
    wrap.appendChild(el('figcaption', 'chart-empty',
      'Not enough months to draw the recorded and projected lines.'));
    return wrap;
  }

  const hasBand = function (p) {
    return p.lower !== null && p.upper !== null && p.lower !== undefined &&
      p.upper !== undefined && isFinite(Number(p.lower)) && isFinite(Number(p.upper));
  };
  const W = 640, H = 200;
  const total = shownHistory.length + ahead.length;
  const values = shownHistory.map(function (p) { return Number(p[1]); });
  ahead.forEach(function (p) {
    values.push(Number(p.value));
    if (hasBand(p)) { values.push(Number(p.lower)); values.push(Number(p.upper)); }
  });
  let lo = Math.min.apply(null, values);
  let hi = Math.max.apply(null, values);
  if (lo === hi) { lo -= 1; hi += 1; }
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const x = function (i) { return PAD.left + (i / Math.max(total - 1, 1)) * innerW; };
  const y = function (v) { return PAD.top + innerH - ((v - lo) / (hi - lo)) * innerH; };
  const lastIndex = shownHistory.length - 1;
  const lastRecorded = shownHistory[lastIndex];
  const firstAhead = ahead[0];
  const finalAhead = ahead[ahead.length - 1];

  const svg = svgEl('svg', {
    viewBox: '0 0 ' + W + ' ' + H, class: 'chart-svg', role: 'img',
    preserveAspectRatio: 'none',
    'aria-label': (opts.label || 'Invoiced revenue') + ': recorded ' +
      monthLabel(shownHistory[0][0]) + ' to ' + monthLabel(lastRecorded[0]) + ', projected ' +
      monthLabel(firstAhead.period) + ' to ' + monthLabel(finalAhead.period),
  });

  // The band: the forecaster's own lower and upper bound for each projected month.
  const banded = [];
  ahead.forEach(function (p, i) { if (hasBand(p)) banded.push([p, lastIndex + 1 + i]); });
  if (banded.length > 0) {
    const top = banded.map(function (pair, k) {
      return (k === 0 ? 'M' : 'L') + x(pair[1]).toFixed(1) + ' ' +
        y(Number(pair[0].upper)).toFixed(1);
    });
    const bottom = banded.slice().reverse().map(function (pair) {
      return 'L' + x(pair[1]).toFixed(1) + ' ' + y(Number(pair[0].lower)).toFixed(1);
    });
    svg.appendChild(svgEl('path', { d: top.concat(bottom).join(' ') + ' Z', class: 'chart-band' }));
  }

  // Where recorded months end.
  const boundaryX = x(lastIndex).toFixed(1);
  svg.appendChild(svgEl('line', {
    x1: boundaryX, x2: boundaryX, y1: PAD.top, y2: (H - PAD.bottom).toFixed(1),
    class: 'chart-boundary',
  }));

  const recordedPath = shownHistory.map(function (p, i) {
    return (i === 0 ? 'M' : 'L') + x(i).toFixed(1) + ' ' + y(Number(p[1])).toFixed(1);
  }).join(' ');
  svg.appendChild(svgEl('path', { d: recordedPath, class: 'chart-path', fill: 'none' }));

  // The projected line starts at the last recorded month, so the two read as one measure.
  const projectedPath = ['M' + x(lastIndex).toFixed(1) + ' ' +
    y(Number(lastRecorded[1])).toFixed(1)].concat(ahead.map(function (p, i) {
    return 'L' + x(lastIndex + 1 + i).toFixed(1) + ' ' + y(Number(p.value)).toFixed(1);
  })).join(' ');
  svg.appendChild(svgEl('path', { d: projectedPath, class: 'chart-forecast-path', fill: 'none' }));

  svg.appendChild(svgEl('circle', {
    cx: x(lastIndex).toFixed(1), cy: y(Number(lastRecorded[1])).toFixed(1), r: 3.5,
    class: 'chart-point',
  }));

  const displays = opts.displays || {};
  const tip = el('p', 'chart-tip');
  tip.setAttribute('role', 'status');
  const step = innerW / Math.max(total - 1, 1);
  const hitFor = function (index, label) {
    const hit = svgEl('rect', {
      x: (x(index) - step / 2).toFixed(1), y: 0, width: Math.max(step, 6).toFixed(1), height: H,
      class: 'chart-hit', tabindex: '0', role: 'button', 'aria-label': 'Show ' + label,
    });
    const show = function () { tip.textContent = label; };
    hit.addEventListener('mouseenter', show);
    hit.addEventListener('focus', show);
    hit.addEventListener('mouseleave', function () { tip.textContent = ''; });
    svg.appendChild(hit);
  };
  shownHistory.forEach(function (p, i) {
    const figure = displays[p[0]] || '';
    hitFor(i, monthLabel(p[0]) + ' (recorded)' + (figure ? ': ' + figure : ''));
  });
  ahead.forEach(function (p, i) {
    const band = p.lower_display && p.upper_display
      ? ', usually between ' + p.lower_display + ' and ' + p.upper_display : '';
    hitFor(lastIndex + 1 + i,
      monthLabel(p.period) + ' (projected): ' + (p.display || fmtMoney(p.value)) + band);
  });

  wrap.appendChild(svg);
  wrap.appendChild(tip);

  const scale = el('div', 'chart-scale');
  scale.appendChild(el('span', 'chart-scale-min', monthLabel(shownHistory[0][0])));
  scale.appendChild(el('span', 'chart-scale-boundary',
    'Recorded to ' + monthLabel(lastRecorded[0]) + ' | projected from ' +
    monthLabel(firstAhead.period)));
  scale.appendChild(el('span', 'chart-scale-max', monthLabel(finalAhead.period)));
  wrap.appendChild(scale);

  const legend = el('p', 'chart-legend');
  legend.appendChild(el('span', 'chart-legend-recorded', 'Solid line: recorded invoiced revenue'));
  legend.appendChild(document.createTextNode(' · '));
  legend.appendChild(el('span', 'chart-legend-projected',
    'Dashed line: projected invoiced revenue'));
  if (banded.length > 0) {
    legend.appendChild(document.createTextNode(' · '));
    legend.appendChild(el('span', 'chart-legend-band', 'Shaded: usual range of the projection'));
  }
  wrap.appendChild(legend);

  const caption = el('figcaption', 'chart-caption');
  caption.textContent =
    shownHistory.length + ' recorded months of invoiced revenue, ' +
    monthLabel(shownHistory[0][0]) + ' to ' + monthLabel(lastRecorded[0]) + ', latest ' +
    fmtMoney(lastRecorded[1]) + '. ' + ahead.length + ' projected months, ' +
    monthLabel(firstAhead.period) + ' to ' + monthLabel(finalAhead.period) + '.' +
    (shownHistory.length < recorded.length
      ? ' Showing the most recent ' + shownHistory.length + ' of ' + recorded.length +
        ' recorded months.'
      : '');
  wrap.appendChild(caption);
  return wrap;
}

/*
 * A ranked breakdown. `rows` is [[label, value], ...]. Ordering is by the value the engine
 * supplied; nothing is combined, and a category recorded as zero stays visible as zero rather
 * than being dropped for looking empty.
 */
export function barChart(rows, options) {
  const opts = options || {};
  const wrap = el('figure', 'chart chart-bar');
  wrap.setAttribute('data-chart', 'bar');

  const data = (rows || []).filter(function (r) { return isFinite(Number(r[1])); });
  if (data.length === 0) {
    wrap.appendChild(el('figcaption', 'chart-empty', 'No breakdown is recorded for this.'));
    return wrap;
  }
  const sorted = data.slice().sort(function (a, b) {
    return Math.abs(Number(b[1])) - Math.abs(Number(a[1]));
  });
  const peak = Math.max.apply(null, sorted.map(function (r) { return Math.abs(Number(r[1])); }));
  // `display` lets the caller supply the engine's own formatted string per row. Where the
  // figure was produced and reconciled server-side, the number printed beside the bar should
  // be that number, not a second rendering of it made here.
  const supplied = opts.display || null;
  const fmt = opts.unit === 'count' ? fmtCount : fmtMoney;

  const list = el('div', 'bar-rows');
  sorted.forEach(function (row) {
    const value = Number(row[1]);
    const item = el('div', 'bar-row');
    item.appendChild(el('span', 'bar-label', row[0]));
    const track = el('span', 'bar-track');
    const fill = el('span', 'bar-fill');
    fill.style.width = peak > 0 ? (Math.abs(value) / peak) * 100 + '%' : '0%';
    if (value < 0) fill.classList.add('bar-fill-negative');
    track.appendChild(fill);
    item.appendChild(track);
    item.appendChild(el('span', 'bar-value',
      supplied && supplied[row[0]] !== undefined ? supplied[row[0]] : fmt(value)));
    list.appendChild(item);
  });
  wrap.appendChild(list);
  if (opts.caption) wrap.appendChild(el('figcaption', 'chart-caption', opts.caption));
  return wrap;
}

/* A single figure, stated plainly. The caveat travels with it, never behind a tooltip. */
export function kpi(label, value, meta) {
  const info = meta || {};
  const card = el('article', 'kpi');
  if (info.trust) card.setAttribute('data-trust', info.trust);
  card.appendChild(el('p', 'kpi-label', label));
  card.appendChild(el('p', 'kpi-value', value || '—'));
  if (info.note) card.appendChild(el('p', 'kpi-note', info.note));
  return card;
}

export { fmtMoney, fmtCount };
