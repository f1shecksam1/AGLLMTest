SELECT jsonb_build_object(
  'cpu', (SELECT row_to_json(c) FROM (
      SELECT ts, usage_percent, temperature_c, freq_mhz
      FROM metrics_cpu
      ORDER BY ts DESC
      LIMIT 1
  ) c),
  'ram', (SELECT row_to_json(r) FROM (
      SELECT ts, used_mb, available_mb, usage_percent
      FROM metrics_ram
      ORDER BY ts DESC
      LIMIT 1
  ) r),
  'gpu', (SELECT row_to_json(g) FROM (
      SELECT ts, utilization_percent, temperature_c, memory_used_mb
      FROM metrics_gpu
      ORDER BY ts DESC
      LIMIT 1
  ) g)
) AS snapshot;
