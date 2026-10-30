# Gunicorn Configuration for Nong Phet AI Smart Guide
import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', 5000)}"
# 2 workers with multiple threads is optimal for Raspberry Pi 5 (4 cores)
workers = int(os.environ.get('WEB_CONCURRENCY', 2))
threads = 4
worker_class = 'gthread'
worker_connections = 1000
timeout = 120
keepalive = 5

accesslog = '-'
errorlog = '-'
loglevel = 'info'

