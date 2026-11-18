import assert from 'node:assert/strict';
import { test } from 'node:test';
import { compareFreshness } from './freshness.mjs';

const deployed = 'a'.repeat(40), latest = 'b'.repeat(40);
test('matching and changed main revisions are distinguishable', () => {
  assert.equal(compareFreshness(deployed, [{sha: deployed}]), 'fresh');
  assert.equal(compareFreshness(deployed, [{sha: latest}]), 'stale');
});
test('missing, malformed or unavailable upstream information is unknown', () => {
  for (const response of [null, [], [{}], [{sha: 'bad'}], {sha: deployed}]) {
    assert.equal(compareFreshness(deployed, response), 'freshnessUnknown');
  }
  assert.equal(compareFreshness('bad', [{sha: deployed}]), 'freshnessUnknown');
});
