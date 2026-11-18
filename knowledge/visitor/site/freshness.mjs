// An unavailable or malformed upstream response is never evidence of freshness.
export function compareFreshness(sourceRevision, commits) {
  const sha = Array.isArray(commits) ? commits[0]?.sha : null;
  if (!/^[a-f0-9]{40}$/.test(sourceRevision) || typeof sha !== 'string' || !/^[a-f0-9]{40}$/.test(sha)) return 'freshnessUnknown';
  return sha === sourceRevision ? 'fresh' : 'stale';
}
