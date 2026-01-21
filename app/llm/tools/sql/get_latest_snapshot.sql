WITH h AS (
  SELECT id, created_at FROM hosts WHERE id = CAST(:host_id AS uuid)
  UNION ALL
  SELECT id, created_at FROM hosts WHERE :host_id IS NULL
),
chosen AS (
  SELECT id FROM h ORDER BY created_at DESC LIMIT 1
)
SELECT jsonb_build_object(
  'host', (SELECT row_to_json(t) FROM (
      SELECT id::text AS id, hostname, os_name, cpu_model, ram_total_mb, gpu_name
      FROM hosts
      WHERE id = (SELECT id FROM chosen)
  ) t),
  'cpu', (SELECT row_to_json(c) FROM (
      SELECT ts, usage_percent, temperature_c, freq_mhz
      FROM metrics_cpu
      WHERE host_id = (SELECT id FROM chosen)
      ORDER BY ts DESC
      LIMIT 1
  ) c),
  'ram', (SELECT row_to_json(r) FROM (
      SELECT ts, used_mb, available_mb, usage_percent
      FROM metrics_ram
      WHERE host_id = (SELECT id FROM chosen)
      ORDER BY ts DESC
      LIMIT 1
  ) r),
  'gpu', (SELECT row_to_json(g) FROM (
      SELECT ts, utilization_percent, temperature_c, memory_used_mb
      FROM metrics_gpu
      WHERE host_id = (SELECT id FROM chosen)
      ORDER BY ts DESC
      LIMIT 1
  ) g)
) AS snapshot;
