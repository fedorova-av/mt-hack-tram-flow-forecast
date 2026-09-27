const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../backend/app/static/index.html'), 'utf8');
const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1].replace(/init\(\);\s*$/, '');
for (const zone of ['Europe/Berlin', 'Europe/Moscow', 'America/New_York', 'UTC']) {
  process.env.TZ = zone;
  for (const [date, last] of [['2025-11-15', '2025-11-30'], ['2025-12-15', '2025-12-31']]) {
    const context = vm.createContext({document: {getElementById: () => ({value: date})}});
    vm.runInContext(script, context);
    const actual = vm.runInContext("currentHorizon = 'month'; JSON.stringify(getDateRange())", context);
    assert.deepEqual(JSON.parse(actual), {from: date.slice(0, 7) + '-01', to: last}, zone);
  }
}
console.log('OK: month boundaries in 4 time zones');
