import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

// Only browser APIs are stubbed; formatting, interval analysis and startup run unchanged.
const elements = new Map();
globalThis.HTMLElement = class {};
globalThis.customElements = { get: name => elements.get(name), define: (name, value) => elements.set(name, value) };
const root = new URL('../custom_components/hdhomerun/frontend/', import.meta.url);
const localization = await readFile(new URL('localize.js', root), 'utf8');
const localeURL = `data:text/javascript;base64,${Buffer.from(localization).toString('base64')}`;
const source = (await readFile(new URL('cards.js', root), 'utf8')).replace("'./localize.js'", JSON.stringify(localeURL));
const { dateTime } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const { localize } = await import(localeURL);
const hass = (language, time_format = '24', time_zone = 'server') => ({
  locale: { language, time_format, time_zone }, config: { time_zone: 'America/New_York' }, states: {},
});

test('English fallback and regional Program/Programme are selected from HA locale', () => {
  assert.equal(localize(hass('en-US'), 'Program'), 'Program');
  assert.equal(localize(hass('en-GB'), 'Program'), 'Programme');
  assert.equal(localize(hass('fr'), 'Program'), 'Program');
  assert.equal(localize(hass('en-GB'), 'Favorites'), 'Favourites');
  assert.equal(localize(hass('en-GB'), '{count} / {total} tuners free', { count: 2, total: 4 }), '2 / 4 tuners free');
});

test('short timestamps respect explicit clock and server zone without midnight 24:00', () => {
  const midnight = new Date('2026-01-02T05:00:00Z');
  assert.match(dateTime(hass('en-US'), midnight), /Jan 2 at 00:00$/);
  assert.match(dateTime(hass('en-US', '12'), midnight, true), /12:00:00\s*AM$/);
  assert.match(dateTime(hass('en-GB', 'language'), midnight), /00:00$/);
  assert.match(dateTime(hass('en-US', 'language'), midnight), /12:00\s*AM$/);
  const local = hass('en-US', '24', 'local');
  const expected = new Intl.DateTimeFormat('en-US', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(midnight);
  assert.ok(dateTime(local, midnight).endsWith(expected));
  const system = dateTime(hass('en-GB', 'system'), midnight);
  const system12 = new Intl.DateTimeFormat(undefined, {hour: 'numeric'}).resolvedOptions().hour12;
  assert.match(system, system12 ? /12:00\s*am$/i : /00:00$/);
});

test('only namespaced cards are registered', () => {
  assert.deepEqual([...elements.keys()].sort(), ['hdhomerun-capacity-card', 'hdhomerun-health-badge', 'hdhomerun-section-card', 'hdhomerun-tuner-card']);
});

function capacity(profile, channel = '7.1', strength = '40', quality = '100', symbol = '100') {
  const card = Object.create(elements.get('hdhomerun-capacity-card').prototype);
  card.config = { signal_profile: profile, quality_tuners: [{ name: 'Tuner 1', entity: 'channel', strength: 'strength', quality: 'quality', symbol: 'symbol' }] };
  card._hass = hass('en-US');
  card._history = Object.fromEntries(Object.entries({ channel, strength, quality, symbol }).map(([entity, s]) => [entity, [{ lu: 1, s }]]));
  return card;
}

test('unknown profiles omit strength thresholds but retain quality and symbol diagnostics', () => {
  assert.deepEqual(capacity(undefined).qualityIntervals(1, 10), []);
  assert.deepEqual(capacity('unknown').qualityIntervals(1, 10), []);
  assert.equal(capacity('antenna').qualityIntervals(1, 10)[0].severity, 2);
  assert.equal(capacity('cable', '7.1', '85').qualityIntervals(1, 10)[0].severity, 1);
  assert.equal(capacity('unknown', '7.1', '40', '60').qualityIntervals(1, 10)[0].severity, 1);
  assert.equal(capacity('unknown', '7.1', '40', '100', '99').qualityIntervals(1, 10)[0].severity, 2);
  for (const channel of ['idle', 'unknown', 'unavailable']) assert.deepEqual(capacity('antenna', channel).qualityIntervals(1, 10), []);
  assert.deepEqual(capacity('antenna', '7.1', 'unknown', 'unavailable', '').qualityIntervals(1, 10), []);
});

test('history startup waits for config and starts when config arrives last', async () => {
  const card = Object.create(elements.get('hdhomerun-capacity-card').prototype);
  card.draw = () => {};
  card.isConnected = true;
  let calls = 0;
  card.hass = { ...hass('en-US'), callWS: async request => {
    calls++;
    assert.deepEqual(request.entity_ids, ['sensor.free']);
    assert.equal(request.type, 'history/history_during_period');
    return {};
  } };
  assert.equal(calls, 0);
  try {
    card.setConfig({ entities: [{entity: 'sensor.free'}], adaptive_history: true });
    await Promise.resolve();
    assert.equal(calls, 1);
    assert.deepEqual([400, 800, 1200].map(width => card.hoursForWidth(width)), [24, 36, 48]);
  } finally { card.disconnectedCallback(); }
});

// Minimal DOM boundary for inspecting public render output without HA or jsdom.
class Node {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.attributes = {}; this.listeners = {}; this.style = {setProperty() {}}; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(key, value) { this.attributes[key] = value; if (key === 'class') this.className = value; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  querySelector(selector) {
    const matches = node => selector.startsWith('.') ? node.className?.split(' ').includes(selector.slice(1)) : node.tagName === selector;
    for (const child of this.children) { if (matches(child)) return child; const nested = child.querySelector?.(selector); if (nested) return nested; }
  }
}
globalThis.document = { createElement: tag => new Node(tag), createElementNS: (_ns, tag) => new Node(tag), createTextNode: text => ({textContent: text}) };
function tuner() {
  const card = Object.create(elements.get('hdhomerun-tuner-card').prototype);
  card.shadowRoot = new Node();
  for (const name of ['title', 'status-icon', 'content']) { const node = new Node(); node.className = name; card.shadowRoot.append(node); }
  card.setConfig({ entity: 'channel', programme: 'program', title: 'Tuner 1', metrics: [{entity: 'rate', name: 'Network rate', unit: 'bit/s', max: 20e6}], details: [{entity: 'frequency', name: 'Frequency', unit: 'MHz'}] });
  return card;
}
function tunerHass(unit, value, frequencyUnit = 'MHz', frequency = '587') {
  const result = hass('en-GB');
  result.states = {
    channel: {state: '7.1'}, program: {state: 'News'},
    rate: {state: value, attributes: {unit_of_measurement: unit}},
    frequency: {state: frequency, attributes: {unit_of_measurement: frequencyUnit}},
  };
  return result;
}

test('network meter preserves HA unit preferences and rescales when units change', () => {
  const card = tuner();
  card.hass = tunerHass('Mbit/s', '6');
  let metric = card.shadowRoot.querySelector('.metric');
  assert.equal(metric.querySelector('.label').textContent, 'Network rate · Scale 0–20 Mbit/s');
  assert.equal(metric.querySelector('.value').textContent, '6 Mbit/s');
  assert.equal(metric.querySelector('.fill').style.width, '30%');
  card.hass = tunerHass('kbit/s', '6000');
  metric = card.shadowRoot.querySelector('.metric');
  assert.equal(metric.querySelector('.label').textContent, 'Network rate · Scale 0–20000 kbit/s');
  assert.equal(metric.querySelector('.fill').style.width, '30%');
  card.hass = tunerHass('MB/s', '0.75');
  metric = card.shadowRoot.querySelector('.metric');
  assert.equal(metric.querySelector('.fill').style.width, '30%');
  assert.equal(metric.querySelector('.value').textContent, '0.75 MB/s');
  assert.equal(card.shadowRoot.querySelector('.programme').querySelector('.label').textContent, 'Programme');
});

test('frequency uses the actual source unit instead of blindly dividing MHz by a million', () => {
  const card = tuner();
  for (const [unit, value] of [['Hz', '587000000'], ['kHz', '587000'], ['MHz', '587'], ['GHz', '0.587']]) {
    card.hass = tunerHass('bit/s', '6000000', unit, value);
    assert.equal(card.shadowRoot.querySelector('.details').querySelector('.value').textContent, '587 MHz');
  }
  card.hass = tunerHass('bit/s', '6000000', null, '587');
  assert.equal(card.shadowRoot.querySelector('.details').querySelector('.value').textContent, '587 MHz');
});

test('idle tuner hides all meters rather than presenting stale readings', () => {
  const card = tuner(), state = tunerHass('Mbit/s', '6');
  state.states.channel.state = 'idle';
  card.hass = state;
  assert.equal(card.shadowRoot.querySelector('.metric'), undefined);
  assert.equal(card.shadowRoot.querySelector('.channel').querySelector('.value').textContent, 'Idle');
});

test('receivers without the optional guide omit the program row', () => {
  const card = tuner();
  card.setConfig({...card.config, programme: undefined});
  card.hass = tunerHass('Mbit/s', '6');
  assert.equal(card.shadowRoot.querySelector('.programme'), undefined);
  assert.equal(card.shadowRoot.querySelector('.metric').querySelector('.value').textContent, '6 Mbit/s');
});

test('history remains full-width integer steps with inspectable transparent reception regions', () => {
  const card = capacity('antenna');
  card.shadowRoot = new Node();
  for (const name of ['title', 'warning-key', 'error-key', 'threshold-key', 'excluded-key', 'select-key', 'chart', 'range', 'legend', 'inspection', 'message']) {
    const node = new Node(); node.className = name; card.shadowRoot.append(node);
  }
  card.shadowRoot.querySelector('.chart').clientWidth = 800;
  card.config.adaptive_history = true;
  card.config.entities = [{entity: 'free', name: 'Free', color: '#00f'}];
  const end = Date.now() / 1000;
  card._history.free = [{lu: end - 200000, s: '4'}, {lu: end - 1000, s: '2'}];
  card._hass.states.free = {state: '2'};
  card.draw();
  assert.equal(card.shadowRoot.querySelector('.range').textContent, '36 hours · Auto');
  const svg = card.shadowRoot.querySelector('svg');
  assert.equal(svg.attributes.viewBox, '0 0 800 205');
  assert.match(svg.querySelector('path').attributes.d, /^ M 30 .+ H .+ V .+ H 790$/);
  const labels = svg.children.filter(child => child.className === 'y-label');
  assert.deepEqual(labels.map(node => node.textContent), ['0', '1', '2', '3', '4']);
  const region = svg.querySelector('.quality-overlay');
  assert.equal(region.attributes['fill-opacity'], .14);
  assert.match(region.attributes['aria-label'], /^Error: Tuner 1 · Signal strength 40%/);
  let prevented = false;
  region.listeners.keydown({key: 'Enter', preventDefault() { prevented = true; }});
  assert.equal(prevented, true);
  assert.equal(card.shadowRoot.querySelector('.inspection').textContent, region.attributes['aria-label']);
  card.config.signal_profile = 'unknown';
  card.draw();
  assert.match(card.shadowRoot.querySelector('.threshold-key').textContent, /No signal strength thresholds/);
  assert.equal(card.shadowRoot.querySelector('.quality-overlay'), undefined);
});
