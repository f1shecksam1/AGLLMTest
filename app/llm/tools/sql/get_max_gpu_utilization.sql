SELECT MAX(utilization_percent) AS max_gpu_utilization_percent
FROM metrics_gpu
WHERE ts >= (now() - (:minutes * interval '1 minute'));
