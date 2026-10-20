// Synthetic DOM/Blob tests only. No human review JSON is written or submitted.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const folder = path.resolve(__dirname, '../docs/reviews/cellfix8-20261020T061934Z-c87bce57');
const review = JSON.parse(fs.readFileSync(path.join(folder, 'semantic-review.json'), 'utf8'));
assert.equal(review.reviewer_kind, 'assistant');
assert.equal(review.human_review_completed, false);
const source = fs.readFileSync(path.join(folder, 'review-form.js'), 'utf8');

async function check() {
  let exports = 0, alerts = 0, blob;
  const save = {};
  const name = {value: ''}, done = {checked: false};
  const cards = review.cases.map(row => {
    const boxes = Object.keys(row.judgments).map(key => ({dataset: {key}, checked: false}));
    const notes = {value: 'TEST_ONLY: synthetic DOM test, no real human signature.'};
    return {boxes, querySelectorAll: () => boxes, querySelector: () => notes};
  });
  const document = {
    querySelector: key => ({'#save': save, '#name': name, '#done': done}[key]),
    querySelectorAll: () => cards,
    createElement: () => ({click: () => {exports++;}}),
  };
  vm.runInNewContext(source, {document, Blob, URL: {
    createObjectURL: value => {blob = value; return 'blob:synthetic-test';}, revokeObjectURL: () => {},
  }, alert: () => {alerts++;}, setTimeout: () => {}, Date, JSON, Object});
  save.onclick();
  assert.equal(exports, 0); assert.equal(alerts, 1);
  name.value = 'TEST_ONLY_NOT_A_HUMAN_SIGNATURE'; done.checked = true;
  save.onclick();
  assert.equal(exports, 0); assert.equal(alerts, 2);
  for (const card of cards) for (const box of card.boxes) box.checked = true;
  save.onclick();
  assert.equal(exports, 1); assert.equal(alerts, 2);
  const synthetic = JSON.parse(await blob.text());
  assert.equal(synthetic.reviewer, 'TEST_ONLY_NOT_A_HUMAN_SIGNATURE');
  assert.equal(synthetic.criteria_sha256, review.criteria_sha256);
  assert.equal(synthetic.predictions_sha256, review.predictions_sha256);
  assert.equal(synthetic.cases.length, 18);
  assert.equal(synthetic.cases.flatMap(c => Object.values(c.judgments)).length, 90);
  assert.ok(synthetic.cases.every(c => Object.values(c.judgments).every(v => v === true)));
  // A failed criterion prevents another export; production admission is unchanged.
  cards[13].boxes[4].checked = false;
  save.onclick();
  assert.equal(exports, 1); assert.equal(alerts, 3);
  console.log('PASS: reviewer/done, incomplete rubric, export/hash binding, failed-criterion guard. No human artifact created.');
}
check().catch(error => {console.error(error);process.exitCode = 1;});
