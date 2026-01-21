SELECT MAX(usage_percent) AS max_cpu_usage_percent
FROM metrics_cpu
WHERE ts >= (now() - (:minutes * interval '1 minute'));
