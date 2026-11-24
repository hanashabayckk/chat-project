"""Server metrics: counters, a messages-per-second rate and uptime."""
import time
from collections import deque

# counters updated by the server while it runs
stats = {"active": 0, "total_connections": 0, "messages": 0,
         "bytes_in": 0, "bytes_out": 0}
recent = deque()          # stores the time of each recent message, used for the rate
start_time = time.time()  # when the server started

# adds one to messages and stores time 
def record_message():
    """Call once for every chat message the server handles."""
    stats["messages"] += 1
    recent.append(time.time())

# drops timestamps older than 10 seconds, then returns all counters plus the rate and uptime.
def snapshot():
    """Return a copy of all metrics, ready to send as JSON."""
    now = time.time()
    while recent and now - recent[0] > 10:   # keep only the last 10 seconds
        recent.popleft()
    return {**stats,
            "msgs_per_sec_last10s": round(len(recent) / 10, 2),
            "uptime_seconds": round(now - start_time)}