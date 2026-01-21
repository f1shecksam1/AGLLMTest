SELECT id::text AS id, hostname, created_at
FROM hosts
ORDER BY created_at DESC;