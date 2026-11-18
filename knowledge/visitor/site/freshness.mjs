// An unavailable or malformed upstream response is never evidence of freshness.
export function compareFreshness(sourceRevision, commits) {
  const sha = Array.isArray(commits) ? commits[0]?.sha : null;
  if (!/^[a-f0-9]{40}$/.test(sourceRevision) || typeof sha !== 'string' || !/^[a-f0-9]{40}$/.test(sha)) return 'freshnessUnknown';
  return sha === sourceRevision ? 'fresh' : 'stale';
}

// The time must come from a successful status for this exact deployed commit.
export function publicationTime(revision, deployment, statuses) {
  if (!/^[a-f0-9]{40}$/.test(revision) || deployment?.sha !== revision || deployment?.environment !== 'github-pages' || !Array.isArray(statuses)) return null;
  if (!statuses.length || statuses.length >= 100 || statuses.some(status => typeof status?.state !== 'string' || typeof status?.created_at !== 'string' || Number.isNaN(Date.parse(status.created_at)))) return null;
  const newest = Math.max(...statuses.map(status => Date.parse(status.created_at)));
  const latest = statuses.filter(status => Date.parse(status.created_at) === newest);
  return latest.length === 1 && latest[0].state === 'success' ? latest[0].created_at : null;
}

export function latestPagesDeployment(revision, deployments) {
  if (!/^[a-f0-9]{40}$/.test(revision) || !Array.isArray(deployments) || !deployments.length || deployments.length >= 100) return null;
  if (deployments.some(item => item?.sha !== revision || item?.environment !== 'github-pages' || !Number.isSafeInteger(item?.id) || item.id <= 0 || typeof item.created_at !== 'string' || Number.isNaN(Date.parse(item.created_at)))) return null;
  const newest = Math.max(...deployments.map(item => Date.parse(item.created_at)));
  const latest = deployments.filter(item => Date.parse(item.created_at) === newest);
  return latest.length === 1 ? latest[0] : null;
}
