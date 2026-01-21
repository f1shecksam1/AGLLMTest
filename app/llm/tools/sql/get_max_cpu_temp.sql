SELECT MAX(temperature_c) AS max_cpu_temp_c
FROM metrics_cpu
WHERE ts >= (now() - (:minutes * interval '1 minute'));
