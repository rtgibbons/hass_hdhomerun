import './cards.js';
import { localize } from './localize.js';

// Registry translation keys are stable even when users rename entities/devices.
class HDHomeRunDashboardStrategy extends HTMLElement {
  static noEditor = true;

  static shouldRegenerate(_config, oldHass, newHass) {
    return oldHass.entities !== newHass.entities || oldHass.devices !== newHass.devices ||
      oldHass.locale?.language !== newHass.locale?.language;
  }

  static getCreateSuggestions() {
    return { title: 'HDHomeRun', icon: 'mdi:television-play' };
  }

  static async generate(config, hass) {
    const t = (key, values) => localize(hass, key, values);
    const registry = await hass.callWS({ type: 'config/entity_registry/list' });
    const entities = registry.filter(entity => entity.platform === 'hdhomerun' &&
      !entity.disabled_by && !entity.hidden_by && entity.config_entry_id);
    const entries = [...new Set(entities.map(entity => entity.config_entry_id))].sort();
    const devices = hass.devices || {};
    const dashboardPath = '/' + window.location.pathname.split('/').filter(Boolean)[0];
    const views = [];
    const section = card => ({ type: 'grid', cards: [card] });
    const group = (title, icon, options) => ({ type: 'custom:hdhomerun-section-card',
      title, icon, ...options });
    const shortcut = (name, icon, tap_action) => ({ type: 'button', name, icon,
      icon_height: '24px', show_state: false, tap_action });
    for (const entry of entries) {
      const owned = entities.filter(entity => entity.config_entry_id === entry);
      const main = owned.filter(entity => !entity.translation_key?.startsWith('tuner_') ||
        entity.translation_key === 'tuner_count');
      const find = (list, key) => list.find(entity => entity.translation_key === key)?.entity_id;
      const id = key => find(main, key);
      const parent = devices[main.find(entity => entity.device_id)?.device_id];
      const name = parent?.name_by_user || parent?.name || 'HDHomeRun';
      const path = `device-${entry}`, maintenance = `maintenance-${entry}`;
      const rows = [
        ['lineup_updated', 'Lineup updated'], ['epg_updated', 'Guide updated'],
        ['epg_coverage_end', 'Coverage ends'], ['epg_last_failure', 'Last guide failure'],
        ['channel_count', 'Channels'], ['fav_channels', 'Favorites'],
        ['disabled_channels', 'Disabled channels'],
      ].filter(([key]) => id(key)).map(([key, label]) => ({ entity: id(key), name: t(label) }));
      const refresh = [['epg_refresh', 'Refresh EPG'], ['refresh_lineup', 'Refresh lineup']]
        .filter(([key]) => id(key)).map(([key, label]) => shortcut(t(label), 'mdi:refresh', {
          action: 'perform-action', perform_action: 'button.press', target: { entity_id: id(key) },
        }));
      const sections = [];
      if (rows.length || refresh.length) sections.push(section(group(t('Guide & lineup'), 'mdi:playlist-check', {
        status_entity: id('epg_status'), rows,
        cards: refresh.length ? [{ type: 'horizontal-stack', cards: refresh }] : [],
      })));
      const qualityTuners = [];
      const tunerDevices = [...new Set(owned.filter(entity => entity.translation_key === 'tuner_status')
        .map(entity => entity.device_id))].sort((a, b) =>
          (devices[a]?.name || a).localeCompare(devices[b]?.name || b, undefined, { numeric: true }));
      for (const device of tunerDevices) {
        const tuner = owned.filter(entity => entity.device_id === device);
        const tid = key => find(tuner, `tuner_${key}`);
        const title = devices[device]?.name_by_user || devices[device]?.name || t('Tuner');
        const metrics = [
          ['signal_strength', 'Signal strength'], ['signal_quality', 'Signal quality'],
          ['symbol_quality', 'Symbol quality'], ['network_rate', 'Network rate'],
        ].filter(([key]) => tid(key)).map(([key, label]) => ({
          entity: tid(key), name: t(label), max: key === 'network_rate' ? 20 : 100,
          unit: key === 'network_rate' ? 'Mbit/s' : '%',
        }));
        sections.push(section({ type: 'custom:hdhomerun-tuner-card', title,
          entity: tid('status'), programme: tid('programme'), metrics,
          details: [['frequency', 'Frequency', 'MHz'], ['target_ip', 'Stream target', '']]
            .filter(([key]) => tid(key)).map(([key, label, unit]) => ({entity: tid(key), name: t(label), unit})),
        }));
        qualityTuners.push({ name: title, entity: tid('status'), strength: tid('signal_strength'),
          quality: tid('signal_quality'), symbol: tid('symbol_quality') });
      }
      const counts = [['tuners_available', 'Available tuners', '#2196f3'], ['tuner_count', 'Total tuners', '#43a047']]
        .filter(([key]) => id(key)).map(([key, label, color]) => ({entity: id(key), name: t(label), color}));
      if (counts.length) sections.push({ type: 'grid', column_span: 3, cards: [{
        type: 'custom:hdhomerun-capacity-card', entities: counts, adaptive_history: true,
        signal_profile: ['antenna', 'cable'].includes(config.signal_profile) ? config.signal_profile : 'unknown',
        quality_tuners: qualityTuners, grid_options: { columns: 'full', rows: 'auto' },
      }] });
      sections.push(section(group(t('Maintenance'), 'mdi:tools', { cards: [
        shortcut(t('Tools & diagnostics'), 'mdi:tools', { action: 'navigate', navigation_path: `${dashboardPath}/${maintenance}` }),
      ] })));
      const badges = [['epg_status', 'epg'], ['tuners_available', 'capacity'],
        ['epg_consecutive_failures', 'failures'], ['channel_scanning', 'scanning']]
        .filter(([key]) => id(key)).map(([key, kind]) => ({
          type: 'custom:hdhomerun-health-badge', entity: id(key), kind,
          ...(kind === 'capacity' ? {total_entity: id('tuner_count')} : {}),
        }));
      views.push({ title: name, path, icon: 'mdi:television', type: 'sections', max_columns: 3, badges, sections });

      const diagnosticCards = ['tuner_count', 'update', 'channel_sources'].filter(key => id(key))
        .map(key => ({ type: 'tile', entity: id(key) }));
      if (parent) diagnosticCards.push(shortcut(t('HDHomeRun device settings'), 'mdi:cog', {
        action: 'navigate', navigation_path: `/config/devices/device/${parent.id}`,
      }));
      const protectedActions = [
        ['channel_scan', 'Channel scan', 'mdi:radar', 'Start a channel scan using the selected source? This may interrupt live TV or recordings.'],
        ['restart', 'Restart HDHomeRun', 'mdi:restart', 'Restart the HDHomeRun tuner device? Active streams and recordings may be interrupted. This does not restart Home Assistant.'],
        ['epg_rotate', 'Rotate EPG URL', 'mdi:link-variant-off', 'Invalidate the current XMLTV and M3U URLs? All players using them will need the new URLs.'],
      ].filter(([key]) => id(key)).map(([key, label, icon, confirmation]) => shortcut(t(label), icon, {
        action: 'perform-action', perform_action: 'button.press', target: {entity_id: id(key)},
        confirmation: {text: t(confirmation)},
      }));
      views.push({ title: `${name} · ${t('Maintenance')}`, path: maintenance, subview: true,
        back_path: `${dashboardPath}/${path}`,
        type: 'sections', max_columns: 2, sections: [
          section(group(t('Device & diagnostics'), 'mdi:information-outline', {
            cards: diagnosticCards,
            note: t('Choose a channel source before starting a scan. Scans and device restarts can interrupt viewing. Rotating the guide URL invalidates existing XMLTV and M3U URLs.'),
          })),
          section(group(t('Protected actions'), 'mdi:shield-alert-outline', {
            cards: protectedActions, note: t('No maintenance action runs merely by opening this page.'),
          })),
        ] });
    }
    if (!views.length) views.push({ title: 'HDHomeRun', path: 'overview', cards: [{ type: 'markdown',
      content: t('No enabled HDHomeRun entities found. Add a receiver in Settings → Devices & services, or check entity visibility.'),
    }] });
    return { title: config.title || 'HDHomeRun', views };
  }
}

if (!customElements.get('ll-strategy-dashboard-hdhomerun')) {
  customElements.define('ll-strategy-dashboard-hdhomerun', HDHomeRunDashboardStrategy);
  window.customStrategies = window.customStrategies || [];
  window.customStrategies.push({ type: 'hdhomerun', strategyType: 'dashboard', name: 'HDHomeRun',
    description: 'HDHomeRun', documentationURL: 'https://github.com/rtgibbons/hass_hdhomerun#dashboard' });
}
