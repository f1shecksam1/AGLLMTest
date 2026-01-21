WITH h AS (
  SELECT id, created_at FROM hosts WHERE id = CAST(:host_id AS uuid)
  UNION ALL
  SELECT id, created_at FROM hosts WHERE :host_id IS NULL
),
chosen AS (
  SELECT id FROM h ORDER BY created_at DESC LIMIT 1
)
SELECT MAX(utilization_percent) AS max_gpu_utilization_percent
FROM metrics_gpu
WHERE host_id = (SELECT id FROM chosen)
  AND ts >= (now() - (:minutes * interval '1 minute'));
