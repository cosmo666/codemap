const { DEFAULT_TITLE } = require('./components');

/** Formats a label for display. */
function formatLabel(id) {
  return DEFAULT_TITLE + ': ' + id;
}

const slugify = (text) => text.toLowerCase().replace(/\s+/g, '-');

module.exports = { formatLabel, slugify };
