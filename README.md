# Real-Time Client-Server Messaging System

CSEN 503 course project (Winter 2026). One laptop runs the server; each team member's phone connects as a client over the same Wi-Fi network and chats in real time.

## Features

- **Two application-layer protocols** on one server: WebSocket + JSON (used by the mobile web page) and a custom raw TCP text protocol (used by `tcp_client.py`).
- **Group chat:** all clients share one room; web and TCP users see each other's messages.
- **Persistent history:** every message is stored in SQLite with a unique increasing ID. A reconnecting client sends its `last_id` and receives only the messages it missed.
- **No loss, no duplicates:** TCP delivery plus stored IDs; duplicates are filtered on the client and on the server.
- **Robust to closed sockets:** one client disconnecting never affects the others.
- **Live metrics** at `/stats` (connections, messages, bytes, messages per second, uptime).

## Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 8000 | HTTP | Mobile web page and `/stats` |
| 8765 | WebSocket (JSON) | Protocol 1, used by the web page |
| 9000 | Raw TCP (text lines) | Protocol 2, used by `tcp_client.py` |

## Quick start

1. Install Python 3 and the dependency:
   ```
   pip install -r requirements.txt
   ```
2. Start the server on the laptop (keep this window open):
   ```
   python server.py
   ```
3. Find the laptop's IP address (`ipconfig` on Windows, the **IPv4 Address** of the Wi-Fi adapter).
4. On each phone, connect to the **same Wi-Fi**, open `http://<laptop-ip>:8000`, enter a name and chat.
5. Optional, chat from a terminal over raw TCP:
   ```
   python tcp_client.py <laptop-ip> <your-name>
   ```
6. Monitoring: open `http://<laptop-ip>:8000/stats`.

If a phone cannot connect, see [docs/network-setup.md](docs/network-setup.md) (firewall rule, hotspot fallback, troubleshooting).

## Protocols

**Protocol 1: WebSocket + JSON (port 8765)**

- Client to server: `{"type":"hello","name":"Ali","last_id":0}` to join, then `{"type":"msg","text":"hi"}`.
- Server to client: `{"type":"msg","id":7,"sender":"Ali","text":"hi","ts":1700000000.0}`.

**Protocol 2: custom TCP text lines (port 9000)**

- Every message is one line ending in `\n`, fields separated by `|`.
- Client to server: `HELLO|name|last_id` and `MSG|text`.
- Server to client: `MSG|id|sender|text` and `ERR|reason`.
- Details: [docs/tcp-protocol.md](docs/tcp-protocol.md).

## Running the performance tests

Start the server first. All tests are in `tests/` and save CSV files to `tests/results/`.

```
python tests/benchmark.py latency --proto ws --n 100
python tests/benchmark.py compare --n 100
python tests/benchmark.py scale --proto ws --clients 1 5 10 25 50 --msgs 30
python tests/benchmark.py --host 127.0.0.1 catchup --proto ws --history 500
python tests/overhead.py
```

- `latency`: one-way message latency (mean, median, p95).
- `compare`: WebSocket vs raw TCP latency.
- `scale`: latency and throughput as the number of clients grows.
- `catchup`: reconnect time versus number of messages replayed (additional feature).
- `overhead.py`: bytes per message for each protocol (run on a fresh server).
- On Windows use `--host 127.0.0.1` for `catchup`; the name `localhost` adds about 2 seconds to connection time.
- The tests store messages in `chat.db`. **Stop the server and delete `chat.db` before a demo** so test messages do not appear in the chat.

## Repository structure

```
server.py            server: HTTP + WebSocket + TCP handlers, SQLite storage, broadcast
metrics.py           counters and the data behind /stats
tcp_client.py        terminal client for the raw TCP protocol
client/index.html    mobile web client (served on port 8000)
requirements.txt     Python dependency (websockets)
tests/               benchmark.py, overhead.py and results/ (CSV output)
docs/                design-report.pdf, network-setup.md, tcp-protocol.md, captures/
```

## Documentation

- [Design report (PDF)](docs/design-report.pdf): design decisions, protocols, additional features, performance results.
- [Network setup and Wireshark analysis](docs/network-setup.md)
- [TCP protocol and metrics notes](docs/tcp-protocol.md)

## Team

| Name | GUC ID | Main contribution |
|------|--------|-------------------|
| Alia Ahmed Hassan | 64-7151 | Server core: SQLite storage, history replay, broadcast, duplicate protection |
| Zeina Tamer | 64-3390 | Mobile web client |
| Hana Shabayek | 64-13684 | Raw TCP protocol, metrics and `/stats`, overhead test |
| Jana Ahmed Nassar | 64-5984 | Network setup, Wireshark analysis, benchmark tests, documentation |
