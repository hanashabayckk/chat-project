"""Bytes the server counts per message: WebSocket+JSON vs raw TCP.
Usage (fresh server, nobody else chatting): python tests/overhead.py [host]
"""
import asyncio, json, sys, urllib.request
from websockets.asyncio.client import connect

HOST = sys.argv[1] if len(sys.argv) > 1 else "localhost"

#settings, so server doesn't replay old messages 
N, TEXT, NO_HISTORY = 50, "hello world", 10**9

#reads /stats page 
def stats():
    """Read the server's own /stats page."""
    return json.loads(urllib.request.urlopen(f"http://{HOST}:8000/stats").read())

#each one from run_ws & run_tcp connect one client read /stats before, send 50 identical messages (waiting for each echo), then read /stats after.
async def run_ws():
    ws = await connect(f"ws://{HOST}:8765")
    await ws.send(json.dumps({"type": "hello", "name": "ovhws", "last_id": NO_HISTORY}))
    await asyncio.sleep(0.3)
    before = stats()
    for _ in range(N):
        await ws.send(json.dumps({"type": "msg", "text": TEXT}))
        await ws.recv()
    after = stats()
    await ws.close()
    return before, after

async def run_tcp():
    reader, writer = await asyncio.open_connection(HOST, 9000)
    writer.write(f"HELLO|ovhtc|{NO_HISTORY}\n".encode())
    await writer.drain()
    await asyncio.sleep(0.3)
    before = stats()
    for _ in range(N):
        writer.write(f"MSG|{TEXT}\n".encode())
        await writer.drain()
        await reader.readline()
    after = stats()
    writer.close()
    return before, after

#divides the byte difference by 50 to get bytes per message in each direction, then prints one line per protocol
async def main():
    for name, fn in (("WebSocket+JSON", run_ws), ("raw TCP", run_tcp)):
        b, a = await fn()
        print(f"{name:15} bytes in/msg: {(a['bytes_in'] - b['bytes_in']) / N:6.1f}"
              f" | bytes out/msg: {(a['bytes_out'] - b['bytes_out']) / N:6.1f}")
    await asyncio.sleep(0.5)

asyncio.run(main())