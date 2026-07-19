const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const appRoot = process.env.APP_ROOT || process.cwd();
const source = fs.readFileSync(`${appRoot}/web/static/js/drop-progress.js`, 'utf8');

function makeElement() {
  return {
    textContent: '',
    style: {},
    classList: {
      values: new Set(),
      add(...items) { items.forEach(item => this.values.add(item)); },
      remove(...items) { items.forEach(item => this.values.delete(item)); },
      contains(item) { return this.values.has(item); },
    },
  };
}

const elements = new Map();
[
  'current-drop', 'drop-value', 'drop-progress-text', 'drop-data-source', 'drop-id',
  'drop-raw-progress', 'drop-last-update', 'drop-progress-bar', 'connection-ping',
  'last-error', 'drop-image-container', 'drop-image', 'drop-image-fallback'
].forEach(id => elements.set(id, makeElement()));

const context = {
  console,
  window: { addEventListener() {} },
  document: {
    hidden: false,
    getElementById: id => elements.get(id) || null,
    addEventListener() {},
  },
  performance: { now: () => 10 },
  Date,
  setInterval() { return 1; },
  clearInterval() {},
  getAuthHeaders: () => ({ Authorization: 'Bearer token' }),
  handleUnauthorizedResponse: response => response.status !== 401,
  clearCurrentDropContext: () => { context.cleared = true; },
  updateCurrentDropContext: (id, name, game) => { context.dropContext = { id, name, game }; },
};
vm.createContext(context);
vm.runInContext(source, context);

let jsonCalled = false;
context.fetch = () => Promise.resolve({
  ok: true,
  status: 200,
  statusText: 'OK',
  json: () => {
    jsonCalled = true;
    return Promise.resolve({
      active_drop: true,
      drop_id: 'drop-1',
      name: 'Drop One',
      game: 'Game One',
      current_minutes: 12,
      required_minutes: 60,
      remaining_minutes: 48,
      progress_percentage: 20,
      source: 'gql',
      image_url: null,
    });
  },
});

context.fetchActiveDropData().then(data => {
  assert(jsonCalled, '200 active-drop response should parse JSON, not be treated as auth failure');
  assert.strictEqual(data.name, 'Drop One');
  assert.strictEqual(elements.get('current-drop').textContent, 'Drop One');
  assert.strictEqual(elements.get('drop-progress-bar').style.width, '20%');

  context.updateDropProgressUI({ active_drop: null, _pingMs: 5, _fetchedAt: new Date() });
  assert.strictEqual(elements.get('current-drop').textContent, 'None');
  assert.strictEqual(elements.get('drop-progress-bar').style.width, '0%');
  assert.strictEqual(elements.get('drop-progress-text').textContent, 'No active drop');
  assert.strictEqual(elements.get('last-error').textContent, 'None');
  console.log('drop progress rendering tests OK');
}).catch(error => {
  console.error(error);
  process.exit(1);
});
