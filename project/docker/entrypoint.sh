#!/bin/sh
set -e

host="${MYSQL_HOST:-db}"
port="${MYSQL_PORT:-3306}"

echo "Waiting for MySQL at ${host}:${port}..."
while ! python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('${host}', ${port})); s.close()" 2>/dev/null; do
  sleep 2
done
echo "MySQL is ready."

exec uvicorn server:app --host 0.0.0.0 --port 8000
