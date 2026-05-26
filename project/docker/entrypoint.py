#!/usr/bin/env python3
import os
import socket
import sys
import time


def wait_for_mysql():
    host = os.getenv("MYSQL_HOST", "db")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    print(f"Waiting for MySQL at {host}:{port}...", flush=True)

    while True:
        try:
            with socket.create_connection((host, port), timeout=2):
                break
        except OSError:
            time.sleep(2)

    print("MySQL is ready.", flush=True)


if __name__ == "__main__":
    wait_for_mysql()
    os.execvp(
        "uvicorn",
        ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"],
    )
