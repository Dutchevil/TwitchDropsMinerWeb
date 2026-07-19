const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const appRoot = process.env.APP_ROOT || process.cwd();
const source = fs.readFileSync(`${appRoot}/web/static/js/campaign-filters.js`, 'utf8');

const checkboxDefaults = {
  'filter-not-linked': { checked: false },
  'filter-upcoming': { checked: false },
  'filter-expired': { checked: false },
  'filter-excluded': { checked: false },
  'filter-finished': { checked: false },
};
let rendered = null;
const context = {
  console,
  window: {
    originalCampaignsData: [],
    updateCampaignsUI: data => { rendered = data; },
  },
  document: {
    getElementById: id => checkboxDefaults[id] || null,
    querySelectorAll: () => [],
    addEventListener() {},
  },
};
vm.createContext(context);
vm.runInContext(source, context);

context.window.originalCampaignsData = [];
context.applyCampaignFilters();
assert.strictEqual(JSON.stringify(rendered), '[]', 'empty campaign data should clear stale campaign cards');

context.window.originalCampaignsData = [
  { id: 'eligible-special', linked: false, eligible: true, active: true, upcoming: false, expired: false, excluded: false, finished: false },
  { id: 'not-linked', linked: false, eligible: false, active: true, upcoming: false, expired: false, excluded: false, finished: false },
];
context.applyCampaignFilters();
assert.strictEqual(JSON.stringify(rendered.map(c => c.id)), '["eligible-special"]', 'eligible campaigns should pass linked filter even if linked=false');

console.log('campaign filter tests OK');
