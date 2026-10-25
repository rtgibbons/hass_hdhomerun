import assert from 'node:assert/strict';
import { test } from 'node:test';

// Strategies are HA custom elements, but generation needs no browser or DOM.
globalThis.HTMLElement = class {};
const elements = new Map();
globalThis.customElements = {get: name => elements.get(name), define: (name, value) => elements.set(name, value)};
globalThis.window = {customStrategies: [], location: {pathname: '/my-receivers'}};
await import('../custom_components/hdhomerun/frontend/strategy.js');
const Strategy = elements.get('ll-strategy-dashboard-hdhomerun');

function fixture(language = 'en') {
  const entities = [];
  const devices = {};
  const states = {};
  function entity(entry, device, key, id = `sensor.${entry}_${key}`, domain = 'sensor') {
    const item = {entity_id: id, platform: 'hdhomerun', config_entry_id: entry, device_id: device, translation_key: key};
    if (domain !== 'sensor') item.entity_id = `${domain}.${entry}_${key}`;
    entities.push(item);
    states[item.entity_id] = {state: '1', attributes: {}};
    return item;
  }
  for (const entry of ['alpha', 'beta']) {
    devices[entry] = {id: entry, name: entry, identifiers: [['hdhomerun', entry]]};
    devices[`${entry}_t0`] = {id: `${entry}_t0`, name: 'Tuner0', via_device_id: entry};
    entity(entry, entry, 'tuners_available', `sensor.renamed_${entry}_free`);
    entity(entry, entry, 'tuner_count');
    entity(entry, entry, 'fav_channels');
    entity(entry, entry, 'channel_scan', undefined, 'button');
    entity(entry, entry, 'restart', undefined, 'button');
    entity(entry, `${entry}_t0`, 'tuner_status', `sensor.renamed_${entry}_channel`);
    for (const key of ['tuner_signal_strength', 'tuner_signal_quality', 'tuner_symbol_quality', 'tuner_network_rate', 'tuner_programme']) entity(entry, `${entry}_t0`, key);
  }
  return {entities, devices, states, locale: {language}, async callWS({type}) {
    assert.equal(type, 'config/entity_registry/list');
    return this.entities;
  }};
}

test('discovers renamed entities and separates multiple receivers without hardcoded IDs', async () => {
  const hass = fixture();
  const config = await Strategy.generate({}, hass);
  const overview = config.views.filter(view => !view.subview);
  assert.equal(overview.length, 2);
  const first = JSON.stringify(overview[0]);
  assert.ok(first.includes('sensor.renamed_alpha_free'));
  assert.ok(first.includes('sensor.renamed_alpha_channel'));
  assert.ok(!first.includes('sensor.renamed_beta'));
  assert.ok(!JSON.stringify(config).includes('undefined'));
  const chart = overview[0].sections.flatMap(s => s.cards).find(c => c.type === 'custom:hdhomerun-capacity-card');
  assert.equal(chart.adaptive_history, true);
  assert.equal(chart.signal_profile, 'unknown');
  assert.equal(chart.quality_tuners.length, 1);
  assert.equal(overview[0].sections.find(s => s.cards.includes(chart)).column_span, 3);
  const maintenanceLink = overview[0].sections.flatMap(s => s.cards).flatMap(c => c.cards || [])
    .find(c => c.tap_action?.action === 'navigate');
  assert.equal(maintenanceLink.tap_action.navigation_path, '/my-receivers/maintenance-alpha');
});

test('omits disabled, hidden and missing optional entities and keeps maintenance protected', async () => {
  const hass = fixture();
  hass.entities.find(e => e.translation_key === 'tuner_programme').disabled_by = 'user';
  hass.entities.find(e => e.translation_key === 'fav_channels').hidden_by = 'user';
  const config = await Strategy.generate({}, hass);
  const text = JSON.stringify(config.views.filter(v => v.path.includes('alpha')));
  assert.ok(!text.includes('sensor.alpha_tuner_programme'));
  assert.ok(!text.includes('sensor.alpha_fav_channels'));
  const maintenance = config.views.find(v => v.subview && v.path.includes('alpha'));
  const actions = maintenance.sections.flatMap(s => s.cards).flatMap(c => c.cards || []);
  const protectedActions = actions.filter(c => c.tap_action?.perform_action === 'button.press');
  assert.equal(protectedActions.length, 2);
  assert.ok(protectedActions.every(c => c.tap_action.confirmation.text.length > 20));
});

test('localizes display labels without changing references and supports empty installations', async () => {
  const us = await Strategy.generate({}, fixture('en'));
  const gb = await Strategy.generate({}, fixture('en-GB'));
  assert.ok(JSON.stringify(us).includes('Favorites'));
  assert.ok(JSON.stringify(gb).includes('Favourites'));
  const refs = config => JSON.stringify(config).match(/sensor\.[a-z_0-9]+/g);
  assert.deepEqual(refs(us), refs(gb));
  const empty = fixture();
  empty.entities = [];
  const config = await Strategy.generate({}, empty);
  assert.ok(config.views[0].cards[0].content.includes('HDHomeRun'));
  assert.equal(window.customStrategies.filter(s => s.type === 'hdhomerun').length, 1);
});

test('regenerates for language and registry changes, not every live reading', () => {
  const old = fixture('en');
  assert.equal(Strategy.shouldRegenerate({}, old, {...old, states: {}}), false);
  assert.equal(Strategy.shouldRegenerate({}, old, {...old, locale: {language: 'en-GB'}}), true);
  assert.equal(Strategy.shouldRegenerate({}, old, {...old, devices: {...old.devices}}), true);
  assert.equal(Strategy.shouldRegenerate({}, old, {...old, entities: {...old.entities}}), true);
});
