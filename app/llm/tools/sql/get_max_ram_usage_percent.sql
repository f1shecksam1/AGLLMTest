SELECT MAX(usage_percent) AS max_ram_usage_percent
FROM metrics_ram
WHERE ts >= (now() - (:minutes * interval '1 minute'));
