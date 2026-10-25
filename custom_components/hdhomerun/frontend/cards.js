import { localize } from './localize.js';

// Adapted from the approved, read-only Media dashboard resource. Keep its layout
// and history inspection behavior without registering the personalized names.
function timeOptions(hass) {
  const locale = hass.locale || {}, preference = locale.time_format;
  const twelve = preference === '12' || preference !== '24' && new Intl.DateTimeFormat(preference === 'system' ? undefined : locale.language || 'en', {hour: 'numeric'}).resolvedOptions().hour12;
  return {hour: twelve ? 'numeric' : '2-digit', minute: '2-digit', hourCycle: twelve ? 'h12' : 'h23', timeZone: locale.time_zone === 'local' ? Intl.DateTimeFormat().resolvedOptions().timeZone || hass.config?.time_zone : hass.config?.time_zone};
}
export function dateTime(hass, date, seconds = false) {
  const options = timeOptions(hass), language = hass.locale?.language || 'en';
  return localize(hass, '{date} at {time}', {
    date: new Intl.DateTimeFormat(language, {month: 'short', day: 'numeric', timeZone: options.timeZone}).format(date),
    time: new Intl.DateTimeFormat(language, {...options, ...(seconds ? {second: '2-digit'} : {})}).format(date),
  });
}
function displayState(hass, state) {
  const messages = {idle: 'Idle', unknown: 'Unknown', unavailable: 'Unavailable', ready: 'Ready', refresh_failed: 'Refresh failed', expired: 'Expired', empty: 'Empty', on: 'On', off: 'Off', loading: 'Loading', refreshing: 'Refreshing'};
  return localize(hass, messages[state] ?? state.replaceAll('_', ' '));
}
const rateUnits = {
  'bit/s': 1, 'kbit/s': 1e3, 'Mbit/s': 1e6, 'Gbit/s': 1e9,
  'B/s': 8, 'kB/s': 8e3, 'MB/s': 8e6, 'GB/s': 8e9,
  'byte/s': 8, 'kbyte/s': 8e3, 'Mbyte/s': 8e6, 'Gbyte/s': 8e9,
  'KiB/s': 8192, 'MiB/s': 8388608, 'GiB/s': 8589934592,
};
const frequencyUnits = {Hz: 1, kHz: 1e3, MHz: 1e6, GHz: 1e9};

class MediaHealthBadge extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'}).innerHTML = `
      <style>
        :host { display: inline-block; max-width: 100%; }
        .chip { --tone: #64748b; display: flex; align-items: center; gap: 8px;
          box-sizing: border-box; min-height: 36px; padding: 8px 12px;
          border-radius: 18px; font: 500 13px/18px var(--paper-font-body1_-_font-family, Roboto, sans-serif);
          color: var(--primary-text-color, #17212b);
          background: color-mix(in srgb, var(--tone) 16%, var(--card-background-color, #fff));
          border: 1px solid color-mix(in srgb, var(--tone) 42%, transparent); }
        .good { --tone: #16a34a; } .info { --tone: #0284c7; }
        .warning { --tone: #d97706; } .error { --tone: #dc2626; }
        ha-icon { color: var(--tone); --mdc-icon-size: 18px; flex: none; }
        .label { white-space: nowrap; }
      </style><span class="chip"><ha-icon></ha-icon><span class="label"></span></span>`;
  }
  setConfig(config) {
    if (!config.entity || !['epg', 'capacity', 'failures', 'scanning'].includes(config.kind)) {
      throw new Error('HDHomeRun health badge requires an entity and supported kind');
    }
    this.config = config;
    this.setAttribute('role', 'status');
    if (this._hass) this.hass = this._hass;
  }
  set hass(hass) {
    this._hass = hass;
    if (!this.config) return;
    const state = hass.states[this.config.entity]?.state ?? 'unavailable';
    const total = Number(hass.states[this.config.total_entity]?.state);
    const numeric = state.trim() === '' ? NaN : Number(state);
    const t = (key, variables) => localize(hass, key, variables);
    const formatted = displayState(hass, state);
    let text, tone = 'neutral', icon = 'mdi:help-circle-outline';
    switch (this.config.kind) {
      case 'epg':
        text = t('EPG {state}', {state: formatted});
        if (state === 'ready') { tone = 'good'; icon = 'mdi:check-circle'; }
        else if (state === 'refresh_failed') { tone = 'warning'; icon = 'mdi:alert-circle'; }
        else if (state === 'expired' || state === 'empty') { tone = 'error'; icon = 'mdi:alert-circle'; }
        break;
      case 'capacity':
        text = t('Tuner capacity {state}', {state: formatted});
        if (Number.isFinite(numeric) && numeric >= 0) {
          text = numeric === 0 ? t('All tuners busy') : Number.isFinite(total) && total > 0
            ? t('{count} / {total} tuners free', {count: numeric, total}) : t(numeric === 1 ? '{count} tuner free' : '{count} tuners free', {count: numeric});
          tone = numeric === 0 ? 'warning' : 'info';
          icon = numeric === 0 ? 'mdi:television-off' : 'mdi:television-play';
        }
        break;
      case 'failures':
        text = t('EPG failures {state}', {state: formatted});
        if (Number.isFinite(numeric) && numeric >= 0) {
          text = numeric === 0 ? t('No EPG failures') : t(numeric === 1 ? '{count} EPG failure' : '{count} EPG failures', {count: numeric});
          tone = numeric === 0 ? 'good' : 'error';
          icon = numeric === 0 ? 'mdi:check-circle' : 'mdi:alert-circle';
        }
        break;
      case 'scanning':
        text = t('Scan status {state}', {state: formatted});
        if (state === 'on') { text = t('Channel scan running'); tone = 'warning'; icon = 'mdi:radar'; }
        else if (state === 'off') { text = t('Not scanning'); icon = 'mdi:television'; }
        break;
    }
    this.shadowRoot.querySelector('.chip').className = `chip ${tone}`;
    this.shadowRoot.querySelector('.label').textContent = text;
    this.shadowRoot.querySelector('ha-icon').icon = icon;
    this.setAttribute('aria-label', text);
  }
}
if (!customElements.get('hdhomerun-health-badge')) customElements.define('hdhomerun-health-badge', MediaHealthBadge);

class MediaTunerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'}).innerHTML = `
      <style>
        :host { display: block; }
        ha-card { display: block; padding: 18px; }
        h2 { font-size: 16px; margin: 0 0 16px; display: flex; align-items: center; gap: 8px; }
        .status-icon { --mdc-icon-size: 22px; color: var(--disabled-text-color, #888); flex: none; }
        .status-icon.active { color: #43a047; }
        .row { display: flex; justify-content: space-between; gap: 16px; align-items: baseline; }
        button.row { width: 100%; border: 0; background: none; color: inherit; font: inherit; cursor: pointer; text-align: start; padding: 0; }
        button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 4px; }
        .label, .note { color: var(--secondary-text-color, #666); }
        .value { text-align: end; overflow-wrap: anywhere; min-width: 0; }
        .channel { margin-bottom: 8px; } .programme { margin-bottom: 18px; }
        .metric { margin-top: 14px; } .metric .row { margin-bottom: 6px; }
        .track { height: 6px; border-radius: 3px; overflow: hidden; background: color-mix(in srgb, var(--meter-color) 18%, transparent); }
        .fill { height: 100%; border-radius: inherit; background: var(--meter-color); transition: width 180ms ease-in-out; }
        .details { border-top: 1px solid var(--divider-color, #ddd); padding-top: 12px; margin-top: 18px; }
        .details .row + .row { margin-top: 10px; }
        .note { font-size: 13px; line-height: 1.5; margin: 10px 0 0; }
      </style><ha-card><h2><ha-icon class="status-icon"></ha-icon><span class="title"></span></h2><div class="content"></div></ha-card>`;
  }
  setConfig(config) {
    if (!config.entity) throw Error('HDHomeRun tuner card requires a channel entity');
    this.config = config;
    if (this._hass) this.hass = this._hass;
  }
  getCardSize() { return 5; }
  getGridOptions() { return {columns: 12, rows: 'auto'}; }
  set hass(hass) {
    this._hass = hass;
    if (!this.config) return;
    const state = entity => hass.states[entity]?.state ?? 'unavailable';
    const known = value => !['unknown', 'unavailable', ''].includes(value);
    const channel = state(this.config.entity);
    const active = known(channel) && channel !== 'idle';
    this.shadowRoot.querySelector('.title').textContent = this.config.title;
    const icon = this.shadowRoot.querySelector('.status-icon');
    icon.icon = active ? 'mdi:television-play' : 'mdi:television';
    icon.className = active ? 'status-icon active' : 'status-icon';
    const content = this.shadowRoot.querySelector('.content');
    content.replaceChildren();
    const row = (name, value, entity, className = '') => {
      const element = document.createElement('button');
      element.type = 'button'; element.className = `row ${className}`;
      const label = document.createElement('span'); label.className = 'label'; label.textContent = name;
      const text = document.createElement('span'); text.className = 'value'; text.textContent = value;
      element.append(label, text);
      element.addEventListener('click', () => this.dispatchEvent(new CustomEvent('hass-more-info', {detail: {entityId: entity}, bubbles: true, composed: true})));
      return element;
    };
    content.append(row(localize(hass, 'Channel'), channel === 'idle' || !known(channel) ? displayState(hass, channel || 'unavailable') : channel, this.config.entity, 'channel'));
    if (!active) {
      const note = document.createElement('p'); note.className = 'note';
      note.textContent = localize(hass, channel === 'idle' ? 'No active channel. Meters appear when this tuner is in use.' : 'Waiting for tuner status. No live readings available.');
      content.append(note); return;
    }
    if (this.config.programme) {
      const programme = state(this.config.programme);
      content.append(row(localize(hass, 'Program'), known(programme) ? programme : '—', this.config.programme, 'programme'));
    }
    for (const metric of this.config.metrics || []) {
      const raw = state(metric.entity), value = known(raw) ? Number(raw) : NaN;
      const numeric = Number.isFinite(value) && value >= 0;
      // Values already use HA's selected unit. Rescale the configured scale,
      // not the reading, when the user changes that preference at runtime.
      const unit = hass.states[metric.entity]?.attributes?.unit_of_measurement || metric.unit;
      const factor = rateUnits[metric.unit], currentFactor = rateUnits[unit];
      const max = Number(metric.max) > 0
        ? factor && currentFactor ? Number(metric.max) * factor / currentFactor : Number(metric.max)
        : unit === '%' ? 100 : currentFactor ? 20e6 / currentFactor : 20;
      const section = document.createElement('div'); section.className = 'metric';
      section.style.setProperty('--meter-color', unit === '%' ? '#43a047' : '#2196f3');
      const label = unit === '%' ? metric.name : localize(hass, '{name} · Scale 0–{max} {unit}', {name: metric.name, max, unit});
      section.append(row(label, numeric ? `${new Intl.NumberFormat(hass.locale?.language || 'en', {maximumFractionDigits: 2}).format(value)} ${unit}` : '—', metric.entity));
      if (numeric) {
        const track = document.createElement('div'); track.className = 'track';
        track.setAttribute('role', 'meter'); track.setAttribute('aria-label', label);
        track.setAttribute('aria-valuemin', '0'); track.setAttribute('aria-valuemax', String(max));
        track.setAttribute('aria-valuenow', String(Math.min(max, value)));
        track.setAttribute('aria-valuetext', `${value} ${unit}`);
        const fill = document.createElement('div'); fill.className = 'fill';
        fill.style.width = `${Math.min(100, value / max * 100)}%`;
        track.append(fill); section.append(track);
      }
      content.append(section);
    }
    const details = document.createElement('div'); details.className = 'details';
    for (const detail of this.config.details || []) {
      const raw = state(detail.entity);
      const sourceUnit = hass.states[detail.entity]?.attributes?.unit_of_measurement;
      const unit = detail.unit || sourceUnit;
      const converted = sourceUnit && frequencyUnits[sourceUnit] && frequencyUnits[unit]
        ? Number(raw) * frequencyUnits[sourceUnit] / frequencyUnits[unit] : Number(raw);
      const value = known(raw) && frequencyUnits[unit] && Number.isFinite(converted)
        ? `${new Intl.NumberFormat(hass.locale?.language || 'en', {maximumFractionDigits: 6}).format(converted)} ${unit}` : known(raw) ? raw : '—';
      details.append(row(detail.name, value, detail.entity));
    }
    content.append(details);
  }
}
if (!customElements.get('hdhomerun-tuner-card')) customElements.define('hdhomerun-tuner-card', MediaTunerCard);

class MediaCapacityCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'}).innerHTML = `
      <style>
        :host { display: block; } ha-card { display: block; padding: 18px; }
        h2 { font-size: 16px; margin: 0 0 16px; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
        h2 ha-icon { --mdc-icon-size: 22px; color: var(--disabled-text-color, #888); }
        .range { margin-left: auto; color: var(--secondary-text-color); font-size: 12px; font-weight: normal; }
        .quality-overlay { cursor: pointer; stroke-width: 1; vector-effect: non-scaling-stroke; } .quality-overlay:focus { outline: none; stroke-width: 3; }
        .quality-key, .inspection { text-align: center; color: var(--secondary-text-color); font-size: 12px; line-height: 1.5; margin-top: 8px; } .inspection:empty { display: none; }
        line, path { pointer-events: none; }
        svg { display: block; width: 100%; height: 205px; overflow: visible; }
        text { fill: var(--secondary-text-color, #666); font: 12px sans-serif; }
        line { stroke: var(--divider-color, #ddd); stroke-width: 1; }
        path { fill: none; stroke-width: 2; vector-effect: non-scaling-stroke; }
        .legend { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px 16px; margin-top: 8px; }
        button { background: none; border: 0; color: var(--primary-text-color); font: inherit; font-size: 12px; cursor: pointer; padding: 4px 0; }
        .dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; margin-right: 5px; }
        .message { color: var(--secondary-text-color); font-size: 13px; text-align: center; }
      </style><ha-card><h2><ha-icon icon="mdi:chart-timeline-variant"></ha-icon><span class="title"></span><span class="range"></span></h2><div class="chart"></div><div class="legend"></div><div class="quality-key"><span class="warning-key" style="color:#d97706"></span> &nbsp; <span class="error-key" style="color:#dc2626"></span><br><span class="threshold-key"></span> · <span class="excluded-key"></span><br><span class="select-key"></span></div><div class="inspection" role="status"></div><div class="message"></div></ha-card>`;
  }
  setConfig(config) { this.config = config; this.start(); this.draw(); }
  getCardSize() { return 4; }
  getGridOptions() { return {columns: 12, rows: 'auto'}; }
  connectedCallback() { this._resizeObserver = new ResizeObserver(() => this.draw()); this._resizeObserver.observe(this); this.start(); }
  disconnectedCallback() { clearInterval(this._timer); this._timer = undefined; this._resizeObserver?.disconnect(); }
  set hass(hass) { this._hass = hass; this.start(); this.draw(); }
  start() {
    if (!this.isConnected || !this._hass || !this.config || this._timer) return;
    this._timer = setInterval(() => this.fetchHistory(), 60000);
    this.fetchHistory();
  }
  async fetchHistory() {
    if (this._pending) return;
    this._pending = true;
    const end = new Date(), start = new Date(end - (this.config.adaptive_history ? 48 : this.config.hours_to_show || 24) * 3600000);
    try {
      this._history = await this._hass.callWS({type: 'history/history_during_period', start_time: start.toISOString(), end_time: end.toISOString(), entity_ids: [...new Set([...this.config.entities.map(x => x.entity), ...(this.config.quality_tuners || []).flatMap(t => [t.entity, t.strength, t.quality, t.symbol])].filter(Boolean))], minimal_response: true, no_attributes: true});
      this._error = false;
    } catch { this._error = true; }
    finally { this._pending = false; this.draw(); }
  }
  hoursForWidth(width) { return this.config.adaptive_history ? width < 600 ? 24 : width < 1000 ? 36 : 48 : this.config.hours_to_show || 24; }
  points(entity) {
    const points = (this._history?.[entity] || []).map(p => ({time: p.lu ?? p.lc, value: p.s}));
    const state = this._hass.states[entity], time = Date.parse(state?.last_changed) / 1000;
    if (Number.isFinite(time) && (!points.length || time > points[points.length - 1].time)) points.push({time, value: state.state});
    return points;
  }
  qualityIntervals(start, end) {
    const tuners = this.config.quality_tuners || [], events = [], values = {}, intervals = [];
    for (const tuner of tuners) for (const key of ['entity', 'strength', 'quality', 'symbol']) {
      for (const point of this.points(tuner[key])) if (point.time <= end) events.push({...point, entity: tuner[key]});
    }
    events.sort((a, b) => a.time - b.time);
    const times = [...new Set([start, ...events.filter(p => p.time > start && p.time < end).map(p => p.time), end])];
    let index = 0;
    for (let i = 0; i < times.length - 1; i++) {
      const time = times[i];
      while (index < events.length && events[index].time <= time) { const p = events[index++]; values[p.entity] = p.value; }
      let severity = 0; const reasons = [];
      for (const tuner of tuners) {
        const channel = values[tuner.entity];
        if (!channel || ['idle', 'unknown', 'unavailable'].includes(channel)) continue;
        for (const [key, label] of [['strength', 'Signal strength'], ['quality', 'Signal quality'], ['symbol', 'Symbol quality']]) {
          const profile = tuner.signal_profile ?? this.config.signal_profile;
          if (key === 'strength' && !['antenna', 'cable'].includes(profile)) continue;
          const raw = values[tuner[key]], value = typeof raw === 'string' && raw.trim() !== '' ? Number(raw) : NaN;
          if (!Number.isFinite(value) || value < 0 || value > 100) continue;
          const [red, green] = key === 'symbol' ? [100, 100] : key === 'quality' ? [50, 70] : profile === 'cable' ? [80, 90] : [50, 75];
          const level = value < red ? 2 : value < green ? 1 : 0;
          if (level) { severity = Math.max(severity, level); reasons.push(tuner.name + ' · ' + localize(this._hass, label) + ' ' + value + '%'); }
        }
      }
      if (!severity) continue;
      const reason = reasons.join('; '), last = intervals[intervals.length - 1];
      if (last && last.end === time && last.severity === severity && last.reason === reason) last.end = times[i + 1];
      else intervals.push({start: time, end: times[i + 1], severity, reason});
    }
    return intervals;
  }
  draw() {
    if (!this.config || !this._hass) return;
    const t = (key, variables) => localize(this._hass, key, variables);
    this.shadowRoot.querySelector('.title').textContent = this.config.title || t('Tuner capacity history');
    this.shadowRoot.querySelector('.warning-key').textContent = '■ ' + t('Reception warning');
    this.shadowRoot.querySelector('.error-key').textContent = '■ ' + t('Reception error');
    this.shadowRoot.querySelector('.threshold-key').textContent = t(this.config.signal_profile === 'antenna' ? 'Antenna thresholds' : this.config.signal_profile === 'cable' ? 'Cable thresholds' : 'No signal strength thresholds · Quality/symbol thresholds only');
    this.shadowRoot.querySelector('.excluded-key').textContent = t('Idle/unknown readings excluded');
    this.shadowRoot.querySelector('.select-key').textContent = t('Select a shaded region for details');
    const number = value => typeof value === 'string' && value.trim() !== '' && Number.isInteger(Number(value)) && Number(value) >= 0 ? Number(value) : null;
    const hours = this.hoursForWidth(this.shadowRoot.querySelector('.chart').clientWidth || 420);
    this.shadowRoot.querySelector('.range').textContent = t(this.config.adaptive_history ? '{hours} hours · Auto' : '{hours} hours', {hours});
    const end = Date.now() / 1000, start = end - hours * 3600;
    const series = this.config.entities.map(entity => ({...entity, points: this.points(entity.entity).map(p => ({...p, value: number(p.value)})), current: number(this._hass.states[entity.entity]?.state)}));
    const values = series.flatMap(s => [s.current, ...s.points.map(p => p.value)]).filter(x => x !== null);
    const max = Math.max(1, ...values), step = Math.max(1, Math.ceil(max / 4)), top = Math.ceil(max / step) * step;
    const ns = 'http://www.w3.org/2000/svg';
    const node = (tag, attributes, text) => {
      const element = document.createElementNS(ns, tag);
      for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
      if (text !== undefined) element.textContent = text;
      return element;
    };
    const width = Math.max(280, this.shadowRoot.querySelector('.chart').clientWidth || 420), right = width - 10;
    const svg = node('svg', {viewBox: `0 0 ${width} 205`, role: 'group', 'aria-label': t('Tuner counts with selectable reception warning and error regions')});
    const x = time => 30 + Math.max(0, Math.min(1, (time - start) / (end - start))) * (right - 30);
    const y = value => 165 - value / top * 150;
    const format = new Intl.DateTimeFormat(this._hass.locale?.language || 'en', {...timeOptions(this._hass), ...(hours > 24 ? {weekday: 'short'} : {})});
    for (const interval of this.qualityIntervals(start, end)) {
      const color = interval.severity === 2 ? '#ef4444' : '#f59e0b';
      const label = t(interval.severity === 2 ? 'Error' : 'Warning') + ': ' + interval.reason + ' · ' + dateTime(this._hass, new Date(interval.start * 1000), true) + ' – ' + dateTime(this._hass, new Date(interval.end * 1000), true);
      const rect = node('rect', {x: x(interval.start), y: 15, width: Math.max(1, x(interval.end) - x(interval.start)), height: 150, fill: color, 'fill-opacity': .14, stroke: color, 'stroke-opacity': .65, class: 'quality-overlay', tabindex: 0, role: 'button', 'aria-label': label});
      rect.append(node('title', {}, label));
      const inspect = () => { this.shadowRoot.querySelector('.inspection').textContent = label; };
      rect.addEventListener('click', inspect);
      rect.addEventListener('keydown', event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); inspect(); } });
      svg.append(rect);
    }
    for (let value = 0; value <= top; value += step) {
      svg.append(node('line', {x1: 30, x2: right, y1: y(value), y2: y(value)}));
      svg.append(node('text', {x: 21, y: y(value) + 4, 'text-anchor': 'end', class: 'y-label'}, String(value)));
    }
    for (let tick = 0; tick <= 4; tick++) {
      const time = start + (end - start) * tick / 4;
      svg.append(node('text', {x: x(time), y: 190, 'text-anchor': tick === 0 ? 'start' : tick === 4 ? 'end' : 'middle'}, format.format(new Date(time * 1000))));
    }
    let hasHistory = false;
    for (const item of series) {
      let path = '', previous = null;
      const first = item.points.findIndex(p => p.time >= start);
      const points = first === -1 ? item.points.slice(-1) : item.points.slice(Math.max(0, first - 1));
      for (const point of points) {
        if (point.time > end) continue;
        if (previous !== null) path += ` H ${x(point.time)}`;
        if (point.value !== null) {
          path += previous === null ? ` M ${x(point.time)} ${y(point.value)}` : ` V ${y(point.value)}`;
          hasHistory = true;
        }
        previous = point.value;
      }
      if (previous !== null) path += ` H ${right}`;
      if (path) svg.append(node('path', {d: path, stroke: item.color}));
    }
    this.shadowRoot.querySelector('.chart').replaceChildren(svg);
    const legend = this.shadowRoot.querySelector('.legend'); legend.replaceChildren();
    for (const item of series) {
      const button = document.createElement('button'); button.type = 'button';
      const dot = document.createElement('span'); dot.className = 'dot'; dot.style.background = item.color;
      button.append(dot, document.createTextNode(`${item.name}: ${item.current ?? '—'}`));
      button.addEventListener('click', () => this.dispatchEvent(new CustomEvent('hass-more-info', {detail: {entityId: item.entity}, bubbles: true, composed: true})));
      legend.append(button);
    }
    this.shadowRoot.querySelector('.message').textContent = this._error ? t('History could not be refreshed; retrying automatically.') : !this._history ? t('Loading recorded history…') : !hasHistory ? t('No recorded history available.') : '';
  }
}
if (!customElements.get('hdhomerun-capacity-card')) customElements.define('hdhomerun-capacity-card', MediaCapacityCard);

class MediaSectionCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'}).innerHTML = `
      <style>
        :host { display: block; }
        ha-card { display: block; padding: 18px; }
        h2 { font-size: 16px; margin: 0 0 16px; display: flex; align-items: center; gap: 8px; }
        ha-icon { --mdc-icon-size: 22px; color: var(--disabled-text-color, #888); flex: none; }
        h2 ha-icon.good { color: #43a047; } h2 ha-icon.warning { color: #d97706; } h2 ha-icon.error { color: #dc2626; }
        .rows { display: grid; gap: 12px; }
        .row { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; width: 100%; padding: 0; border: 0; background: none; color: inherit; font: inherit; text-align: start; }
        button.row { cursor: pointer; min-height: 28px; }
        button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 3px; }
        .label { color: var(--secondary-text-color, #666); display: flex; align-items: center; gap: 8px; }
        .value { text-align: end; overflow-wrap: anywhere; min-width: 0; }
        .children { display: grid; gap: 8px; }
        .rows:not(:empty) + .children:not(:empty) { border-top: 1px solid var(--divider-color, #ddd); padding-top: 12px; margin-top: 16px; }
        .children > * { --ha-card-border-width: 0px; --ha-card-box-shadow: none; min-width: 0; }
        .note { color: var(--secondary-text-color, #666); font-size: 13px; line-height: 1.5; margin: 14px 0 0; }
        .note:empty { display: none; }
      </style>
      <ha-card><h2><ha-icon class="status-icon"></ha-icon><span class="title"></span></h2><div class="rows"></div><div class="children"></div><p class="note"></p></ha-card>`;
    this._cards = [];
  }
  setConfig(config) {
    this.config = config;
    this.shadowRoot.querySelector('.title').textContent = config.title;
    this.shadowRoot.querySelector('.status-icon').icon = config.icon;
    this.shadowRoot.querySelector('.note').textContent = config.note || '';
    this._cards = [];
    this.shadowRoot.querySelector('.children').replaceChildren();
    if (config.cards?.length) this.loadCards(config);
    if (this._hass) this.hass = this._hass;
  }
  async loadCards(config) {
    const helpers = await window.loadCardHelpers();
    if (this.config !== config) return;
    this._cards = config.cards.map(card => helpers.createCardElement(card));
    for (const card of this._cards) if (this._hass) card.hass = this._hass;
    this.shadowRoot.querySelector('.children').replaceChildren(...this._cards);
  }
  getCardSize() { return 4; }
  getGridOptions() { return {columns: 12, rows: 'auto'}; }
  set hass(hass) {
    this._hass = hass;
    if (!this.config) return;
    const status = hass.states[this.config.status_entity]?.state;
    const tone = status === 'ready' ? 'good' : status === 'refresh_failed' ? 'warning' : ['expired', 'empty'].includes(status) ? 'error' : '';
    this.shadowRoot.querySelector('.status-icon').className = 'status-icon ' + tone;
    const rows = this.shadowRoot.querySelector('.rows'); rows.replaceChildren();
    for (const item of this.config.rows || []) {
      const state = hass.states[item.entity];
      const row = document.createElement(item.entity ? 'button' : 'div'); row.className = 'row';
      if (item.entity) {
        row.type = 'button';
        row.addEventListener('click', () => this.dispatchEvent(new CustomEvent('hass-more-info', {detail: {entityId: item.entity}, bubbles: true, composed: true})));
      }
      const label = document.createElement('span'); label.className = 'label';
      if (item.icon) { const icon = document.createElement('ha-icon'); icon.icon = item.icon; label.append(icon); }
      label.append(document.createTextNode(item.name));
      const value = document.createElement('span'); value.className = 'value';
      const date = state?.attributes.device_class === 'timestamp' ? new Date(state.state) : null;
      value.textContent = item.entity ? state ? date && Number.isFinite(date.getTime()) ? dateTime(hass, date) : hass.formatEntityState(state) : localize(hass, 'Unavailable') : item.value;
      row.append(label, value); rows.append(row);
    }
    for (const card of this._cards) card.hass = hass;
  }
}
if (!customElements.get('hdhomerun-section-card')) customElements.define('hdhomerun-section-card', MediaSectionCard);
