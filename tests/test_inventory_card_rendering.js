const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const appRoot = process.env.APP_ROOT || process.cwd();
const source = fs.readFileSync(`${appRoot}/web/static/js/lazy-loader.js`, 'utf8');
const context = {
  console,
  window: {},
  document: {
    createElement: () => ({ className: '', innerHTML: '', style: {}, appendChild() {} }),
    querySelectorAll: () => []
  },
  IntersectionObserver: function () { this.observe = () => {}; this.disconnect = () => {}; },
  setTimeout,
  Date,
};
vm.createContext(context);
vm.runInContext(source, context);

const zeroMinuteDrop = {
  id: 'zero-drop',
  name: 'I Got Your Back',
  game: 'League of Legends',
  current_minutes: 0,
  required_minutes: 0,
  image_url: null,
};
const zeroCard = context.createDropCard(zeroMinuteDrop, 'pending');
assert(!zeroCard.innerHTML.includes('NaN%'), 'zero-minute drops must not render NaN%');
assert(zeroCard.innerHTML.includes('0%'), 'zero-minute drops should render 0%');
assert(!zeroCard.innerHTML.includes('claim-drop-btn'), 'zero-minute pending drops must not render claim button');
assert(!zeroCard.innerHTML.includes('>Claim<'), 'zero-minute pending drops must not appear claimable');

const readyDrop = {
  id: 'ready-drop',
  name: 'Ready Drop',
  game: 'Test Game',
  current_minutes: 60,
  required_minutes: 60,
  image_url: null,
};
const readyCard = context.createDropCard(readyDrop, 'pending');
assert(readyCard.innerHTML.includes('100%'), 'ready drops should render 100%');
assert(readyCard.innerHTML.includes('claim-drop-btn'), 'ready drops should render claim button');
assert(readyCard.innerHTML.includes('> Claim'), 'ready drops should say Claim, not Claimed');

console.log('inventory card rendering tests OK');
