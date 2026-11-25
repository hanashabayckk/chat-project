"""Benchmark tests for the chat server (Student 4: network, testing and report).

Measures three performance metrics for the report:
  1. latency     - how long a message takes from sender to receiver
  2. compare     - the same latency test over both protocols (WebSocket+JSON vs raw TCP)
  3. scale       - latency/throughput as the number of connected clients grows

How it measures latency:
  A "sender" client puts the current time (time.perf_counter) inside the message text.
  A "receiver" client reads the broadcast and subtracts that time from the time it
  received it. Both clients live in this one script, so they share the same clock and
  the result is a true one-way latency (sender -> server -> receiver).

Usage (server must already be running):
  python tests/benchmark.py latency --host localhost --proto ws  --n 100
  python tests/benchmark.py compare --host localhost --n 100
  python tests/benchmark.py scale   --host localhost --proto ws  --clients 1 5 10 25 50 --msgs 30

Results are printed and saved as CSV files in tests/results/.
"""
import argparse
import asyncio
import csv
import json
import os
import statistics
import time
import urllib.request

from websockets.asyncio.client import connect

WS_PORT, TCP_PORT, HTTP_PORT = 8765, 9000, 8000
NO_HISTORY = 10**9          # "last_id" so large that the server replays no old messages
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


# ---------------------------------------------------------------- test client
class Client:
    """One test client speaking either protocol ('ws' or 'tcp').

    on_msg(sender, text) is called for every chat message the server sends us.
    """

    def __init__(self, proto, host, name, on_msg):
        self.proto, self.host, self.name, self.on_msg = proto, host, name, on_msg

    async def start(self):
        if self.proto == "ws":
            # Protocol 1: WebSocket + JSON. First message is a "hello" with our name.
            self.ws = await connect(f"ws://{self.host}:{WS_PORT}")
            await self.ws.send(json.dumps({"type": "hello", "name": self.name,
                                           "last_id": NO_HISTORY}))
            self.task = asyncio.create_task(self._ws_reader())
        else:
            # Protocol 2: raw TCP, text lines "HELLO|name|last_id\n" and "MSG|text\n".
            self.reader, self.writer = await asyncio.open_connection(self.host, TCP_PORT)
            self.writer.write(f"HELLO|{self.name}|{NO_HISTORY}\n".encode())
            await self.writer.drain()
            self.task = asyncio.create_task(self._tcp_reader())

    async def _ws_reader(self):
        try:
            async for raw in self.ws:
                m = json.loads(raw)
                if m.get("type") == "msg":
                    self.on_msg(m["sender"], m["text"])
        except Exception:
            pass

    async def _tcp_reader(self):
        try:
            while line := await self.reader.readline():
                # server line format: MSG|id|sender|text
                parts = line.decode().rstrip("\n").split("|", 3)
                if parts[0] == "MSG" and len(parts) == 4:
                    self.on_msg(parts[2], parts[3])
        except Exception:
            pass

    async def send(self, text):
        if self.proto == "ws":
            await self.ws.send(json.dumps({"type": "msg", "text": text}))
        else:
            self.writer.write(f"MSG|{text}\n".encode())
            await self.writer.drain()

    async def close(self):
        self.task.cancel()
        try:
            if self.proto == "ws":
                await self.ws.close()
            else:
                self.writer.close()
        except Exception:
            pass


# ------------------------------------------------------------ core measurement
async def measure(proto, host, n_receivers, n_msgs, timeout=5.0):
    """Send n_msgs one at a time; wait until all n_receivers got each one.

    Returns (latencies_ms, lost, elapsed_seconds).
    """
    latencies = []                  # one entry per (message, receiver) delivery
    waiting = {}                    # seq -> [receivers still missing, future]

    def on_receive(sender, text):
        if not text.startswith("bench:"):
            return                  # ignore anything that is not our test message
        _, seq, t_sent = text.split(":")
        entry = waiting.get(int(seq))
        if entry is None:
            return
        latencies.append((time.perf_counter() - float(t_sent)) * 1000)   # ms
        entry[0] -= 1
        if entry[0] == 0 and not entry[1].done():
            entry[1].set_result(True)

    sender = Client(proto, host, "bench_sender", lambda s, t: None)
    receivers = [Client(proto, host, f"bench_recv{i}", on_receive) for i in range(n_receivers)]
    await sender.start()
    for r in receivers:
        await r.start()
    await asyncio.sleep(0.5)        # let the server register every client

    lost = 0
    loop = asyncio.get_running_loop()
    start = time.perf_counter()
    for seq in range(n_msgs):
        fut = loop.create_future()
        waiting[seq] = [n_receivers, fut]
        await sender.send(f"bench:{seq}:{time.perf_counter()}")
        try:
            await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            lost += waiting[seq][0]             # deliveries that never arrived
    elapsed = time.perf_counter() - start

    for c in [sender] + receivers:
        await c.close()
    return latencies, lost, elapsed


def summarize(latencies):
    """Return mean / median / p95 / min / max (all in ms)."""
    if not latencies:
        return dict(mean=0, median=0, p95=0, min=0, max=0)
    s = sorted(latencies)
    return dict(mean=statistics.mean(s), median=statistics.median(s),
                p95=s[int(0.95 * (len(s) - 1))], min=s[0], max=s[-1])


def save_csv(filename, header, rows):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, filename)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"saved -> {path}")


def server_stats(host):
    """Read the server's own /stats page (Student 3's metrics)."""
    try:
        with urllib.request.urlopen(f"http://{host}:{HTTP_PORT}/stats", timeout=3) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


# ------------------------------------------------------------------- commands
async def cmd_latency(args):
    lat, lost, elapsed = await measure(args.proto, args.host, 1, args.n)
    s = summarize(lat)
    print(f"\nLatency over {args.proto.upper()} ({args.n} messages, 1 receiver)")
    print(f"  mean {s['mean']:.2f} ms | median {s['median']:.2f} ms | p95 {s['p95']:.2f} ms "
          f"| min {s['min']:.2f} | max {s['max']:.2f} | lost {lost}")
    save_csv(f"latency_{args.proto}.csv",
             ["protocol", "messages", "mean_ms", "median_ms", "p95_ms", "min_ms", "max_ms", "lost"],
             [[args.proto, args.n, round(s["mean"], 3), round(s["median"], 3),
               round(s["p95"], 3), round(s["min"], 3), round(s["max"], 3), lost]])


async def cmd_compare(args):
    rows = []
    print(f"\nProtocol comparison ({args.n} messages each, 1 receiver)")
    print(f"{'protocol':<10}{'mean ms':>10}{'median ms':>12}{'p95 ms':>10}{'lost':>7}")
    for proto in ("ws", "tcp"):
        lat, lost, _ = await measure(proto, args.host, 1, args.n)
        s = summarize(lat)
        print(f"{proto:<10}{s['mean']:>10.2f}{s['median']:>12.2f}{s['p95']:>10.2f}{lost:>7}")
        rows.append([proto, args.n, round(s["mean"], 3), round(s["median"], 3),
                     round(s["p95"], 3), lost])
        await asyncio.sleep(0.5)
    save_csv("protocol_comparison.csv",
             ["protocol", "messages", "mean_ms", "median_ms", "p95_ms", "lost"], rows)


async def cmd_scale(args):
    rows = []
    print(f"\nScalability over {args.proto.upper()} ({args.msgs} messages per step)")
    print(f"{'clients':>8}{'mean ms':>10}{'p95 ms':>10}{'lost':>7}{'deliveries/s':>14}")
    for n in args.clients:
        lat, lost, elapsed = await measure(args.proto, args.host, n, args.msgs)
        s = summarize(lat)
        rate = len(lat) / elapsed if elapsed else 0
        print(f"{n:>8}{s['mean']:>10.2f}{s['p95']:>10.2f}{lost:>7}{rate:>14.1f}")
        rows.append([n, args.msgs, round(s["mean"], 3), round(s["p95"], 3), lost, round(rate, 1)])
        await asyncio.sleep(0.5)
    print("\nserver /stats at the end:", server_stats(args.host))
    save_csv(f"scalability_{args.proto}.csv",
             ["receivers", "messages", "mean_ms", "p95_ms", "lost", "deliveries_per_sec"], rows)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="localhost", help="server IP (default: localhost)")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("latency", help="latency of one protocol")
    a.add_argument("--proto", choices=["ws", "tcp"], default="ws")
    a.add_argument("--n", type=int, default=100, help="number of messages")
    a.set_defaults(fn=cmd_latency)

    b = sub.add_parser("compare", help="WebSocket vs TCP latency")
    b.add_argument("--n", type=int, default=100)
    b.set_defaults(fn=cmd_compare)

    c = sub.add_parser("scale", help="performance as clients increase")
    c.add_argument("--proto", choices=["ws", "tcp"], default="ws")
    c.add_argument("--clients", type=int, nargs="+", default=[1, 5, 10, 25, 50])
    c.add_argument("--msgs", type=int, default=30, help="messages per step")
    c.set_defaults(fn=cmd_scale)

    args = p.parse_args()
    asyncio.run(args.fn(args))


if __name__ == "__main__":
    main()
