"""Real-time chat server (CSEN 503).
Three listeners, one shared chat room (group chat) + SQLite history:
  - WebSocket + JSON   (port 8765)  -> protocol 1, used by the phone web page
  - Raw TCP + text     (port 9000)  -> protocol 2, custom "MSG|..." lines
  - HTTP               (port 8000)  -> serves the web page and /stats metrics
"""
import asyncio, json, sqlite3, threading, time, functools
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from websockets.asyncio.server import serve
import metrics

HOST, HTTP_PORT, WS_PORT, TCP_PORT = "0.0.0.0", 8000, 8765, 9000
MAX_NAME = 20      
MAX_TEXT = 500     
# ---------- storage: every message gets a unique increasing id ----------
db = sqlite3.connect("chat.db", check_same_thread=False)
db.execute("CREATE TABLE IF NOT EXISTS messages("
           "id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT, text TEXT, ts REAL)")

def save(sender, text):
    cur = db.execute("INSERT INTO messages(sender,text,ts) VALUES(?,?,?)",
                     (sender, text, time.time()))
    db.commit()
    return cur.lastrowid, time.time()

def history_after(last_id):
    return db.execute("SELECT id,sender,text,ts FROM messages WHERE id>? ORDER BY id",
                      (last_id,)).fetchall()

# ---------- connected clients: each has an async send(id,sender,text,ts) ----------
clients = set()
seen_ids = set()   # (name, client_id) pairs already processed, used to ignore duplicates
async def broadcast(mid, sender, text, ts):
    for c in list(clients):
        try:
            await c.send(mid, sender, text, ts)
        except Exception:      # one broken client must not affect the others
            clients.discard(c)

async def handle_message(name, text, client_id=None):
    text = text.strip()
    if not text:
        return
    if client_id:                       # only clients that send an id get protection
        key = (name, client_id)
        if key in seen_ids:             # already processed, so ignore the repeat
            return
        seen_ids.add(key)
    mid, ts = save(name, text)
    metrics.record_message()
    await broadcast(mid, name, text, ts)
  
class WSClient:
    def __init__(self, ws): self.ws = ws
    async def send(self, mid, sender, text, ts):
        data = json.dumps({"type": "msg", "id": mid, "sender": sender, "text": text, "ts": ts})
        metrics.stats["bytes_out"] += len(data)
        await self.ws.send(data)

class TCPClient:
    def __init__(self, writer): self.w = writer
    async def send(self, mid, sender, text, ts):
        data = f"MSG|{mid}|{sender}|{text}\n".encode()
        metrics.stats["bytes_out"] += len(data)
        self.w.write(data)
        await self.w.drain()

# ---------- protocol 1: WebSocket + JSON ----------
# client -> {"type":"hello","name":"Ali","last_id":0} then {"type":"msg","text":"hi"}
async def ws_handler(ws):
    client, name = WSClient(ws), None
    metrics.stats["active"] += 1; metrics.stats["total_connections"] += 1
    try:
        async for raw in ws:
            metrics.stats["bytes_in"] += len(raw)
            m = json.loads(raw)
            if m["type"] == "hello":
                name = m["name"]
                for row in history_after(int(m.get("last_id", 0))):   # catch-up on reconnect
                    await client.send(*row)
                clients.add(client)
            elif m["type"] == "msg" and name:
                await handle_message(name, m["text"])
    except Exception as e:
        print("ws client error:", e)
    finally:
        clients.discard(client); metrics.stats["active"] -= 1

# ---------- protocol 2: custom TCP text lines ----------
# client -> "HELLO|name|last_id\n" then "MSG|text\n"
# the next line is a fn ran once for each client that connects over TCP & reader is how the server receives bytes from that client, and writer is how it sends bytes back
async def tcp_handler(reader, writer):

    # Creating a TCPclient obj that wraps the connection , none is his name
    client, name = TCPClient(writer), None

    # metrics update where active= n of clients that are connected rn & total_connection= n of clients that has ever connected
    metrics.stats["active"] += 1; metrics.stats["total_connections"] += 1

    try:
        # waits until receives lines ending in /n & this is the protocol framing, when disconnected returnd an empty val & loop ends
        while line := await reader.readline():

            # Adds the size of the received line to the bytes-received counter
            metrics.stats["bytes_in"] += len(line)

             # Turns the raw bytes into text, removes the trailing newline, and splits at most 2 times
            parts = line.decode().rstrip("\n").split("|", 2)
            if parts[0] == "HELLO" and len(parts) == 3:
                name = parts[1].strip()
                if not name or len(name) > MAX_NAME:
                    
                    # the client's outgoing connection.fn queues the bytes(bytes"error message then end line to know it's complete")
                    writer.write(b"ERR|invalid name\n")

                    #lets the server serve other clients while waiting   the client's outgoing connection.fn waits until the queued bytes have actually been sent
                    await writer.drain()

                    break                      # closes this client only
   
                for row in history_after(int(parts[2])):
                    await client.send(*row)
                clients.add(client)
            elif parts[0] == "MSG" and name and len(parts) >= 2:
                # rebuilds the message text
                text = "|".join(parts[1:])

                if len(text) > MAX_TEXT:
                    # error line queued for this client only 
                    writer.write(b"ERR|message too long\n")

                    #waiting for error code to be sent 
                    await writer.drain()

                else:
                    # saves the message and broadcasts it to everyone 
                    await handle_message(name, text)
    except Exception as e:
        print("tcp client error:", e)
    finally:
        clients.discard(client); metrics.stats["active"] -= 1
        writer.close()

# ---------- HTTP: static page + /stats ----------
class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/stats":
            body = json.dumps(metrics.snapshot(), indent=2).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers(); self.wfile.write(body)
        else:
            super().do_GET()
    def log_message(self, *a): pass

async def main():
    http = ThreadingHTTPServer((HOST, HTTP_PORT), functools.partial(Handler, directory="client"))
    threading.Thread(target=http.serve_forever, daemon=True).start()
    tcp = await asyncio.start_server(tcp_handler, HOST, TCP_PORT)
    async with serve(ws_handler, HOST, WS_PORT):
        print(f"Web page: http://<laptop-ip>:{HTTP_PORT}   stats: /stats")
        print(f"WebSocket: {WS_PORT}   raw TCP: {TCP_PORT}")
        async with tcp:
            await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
