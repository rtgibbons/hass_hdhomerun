// Natural US-English messages are the bundled fallback catalog. Only regional
// vocabulary differs; neither cards nor strategy need a translation request.
const enGB = {
  'Program': 'Programme',
  'Programs': 'Programmes',
  'Program guide': 'Programme guide',
  'EPG programs': 'EPG programmes',
  'Favorites': 'Favourites',
};

/** English (US) fallback, with explicit British English vocabulary. */
export function localize(hass, key, variables = {}) {
  const language = (hass?.locale?.language || 'en').toLowerCase().replaceAll('_', '-');
  const british = language === 'en-gb' || language.startsWith('en-gb-');
  const template = british && Object.hasOwn(enGB, key) ? enGB[key] : key;
  return template.replace(/\{(\w+)\}/g, (match, name) => Object.hasOwn(variables, name) ? String(variables[name]) : match);
}
