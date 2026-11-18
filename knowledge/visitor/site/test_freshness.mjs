import assert from 'node:assert/strict';
import { test } from 'node:test';
import { compareFreshness, latestPagesDeployment, publicationTime } from './freshness.mjs';

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

test('publication time requires success for the exact Pages deployment', () => {
  const deployment = {sha: deployed, environment: 'github-pages'};
  const statuses = [{state: 'success', created_at: '2026-11-18T10:30:00Z'}];
  assert.equal(publicationTime(deployed, deployment, statuses), '2026-11-18T10:30:00Z');
  assert.equal(publicationTime(latest, deployment, statuses), null);
  assert.equal(publicationTime(deployed, {...deployment, environment: 'preview'}, statuses), null);
  assert.equal(publicationTime(deployed, deployment, [{state: 'failure', created_at: '2026-11-18T10:31:00Z'}, ...statuses]), null);
  assert.equal(publicationTime(deployed, deployment, [{state: 'success', created_at: 'invalid'}]), null);
  assert.equal(publicationTime(deployed, deployment, [...statuses, {state: 'failure', created_at: '2026-11-18T10:31:00Z'}]), null);
  assert.equal(publicationTime(deployed, deployment, [...statuses, {state: 'failure', created_at: '2026-11-18T10:30:00Z'}]), null);
  assert.equal(publicationTime(deployed, deployment, [...statuses, ...statuses]), null);
  assert.equal(publicationTime(deployed, deployment, null), null);
});

test('only an unambiguous latest deployment for this commit and environment is eligible', () => {
  const older = {id: 1, sha: deployed, environment: 'github-pages', created_at: '2026-11-18T10:00:00Z'};
  const newer = {...older, id: 2, created_at: '2026-11-18T11:00:00Z'};
  assert.equal(latestPagesDeployment(deployed, [older, newer]), newer);
  assert.equal(latestPagesDeployment(deployed, [older, {...older, id: 3}]), null);
  assert.equal(latestPagesDeployment(deployed, [{...newer, sha: latest}]), null);
  assert.equal(latestPagesDeployment(deployed, [{...newer, id: -1}]), null);
  assert.equal(latestPagesDeployment(deployed, []), null);
});
