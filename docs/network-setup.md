# Network Setup and Wireshark Analysis

How the laptop (server) and the phones (clients) connect, and what packet captures show at the network and transport layers.

## 1. Network layout

- **Server:** one Windows laptop running `python server.py`
- **Clients:** team members' phones using a mobile browser (web client), plus `tcp_client.py` for the raw TCP protocol
- **Network:** one home Wi-Fi network, `192.168.1.0/24` (subnet mask `255.255.255.0`), router/gateway `192.168.1.1`
- **Addresses used in testing:** laptop `192.168.1.8`, phone `192.168.1.4` (assigned by the router, so they can change)

## 2. Ports used by the server

| Port | Protocol | Purpose |
|------|----------|---------|
| 8000 | HTTP | Serves the web client page and the `/stats` metrics page |
| 8765 | WebSocket (over TCP) | Chat messages from the web client (JSON) |
| 9000 | Raw TCP | Chat messages from `tcp_client.py` (custom text protocol) |

## 3. Connecting a phone, step by step

1. Start the server on the laptop: `python server.py`. It prints the three ports above.
2. Find the laptop's IP: run `ipconfig` and read the **IPv4 Address** under *Wireless LAN adapter Wi-Fi*.
3. Connect the phone to the **same Wi-Fi network** and turn mobile data off.
4. Open `http://<laptop-ip>:8000` in the phone browser (use `http`, not `https`) and enter a name.
5. Send a message and check that it appears on the laptop browser as well, and the other way round.

## 4. Troubleshooting notes

- **`ERR_CONNECTION_REFUSED`:** nothing is listening on the port. The server was not running (window closed or stopped with Ctrl+C). Restart it with `python server.py`.
- **Page times out on the phone:** the Windows firewall may block incoming connections. Allow the ports from an administrator Command Prompt:
  ```
  netsh advfirewall firewall add rule name="Chat ports" dir=in action=allow protocol=TCP localport=8000,8765,9000
  ```
  Also check that the Wi-Fi network profile in Windows is set to *Private*.
- **Wi-Fi blocks device-to-device traffic (client isolation):** common on university or guest networks. Use a phone hotspot and connect both the laptop and the phone to it.
- **The IP changed:** the router may give the laptop a new address after reconnecting. Run `ipconfig` again.

## 5. Wireshark analysis

Capture taken on the laptop's Wi-Fi adapter while a phone connected to the chat (display filters `tcp.port == 8765` and `tcp.port == 51405`, the phone's source port for that connection). Screenshots are in `docs/captures/`.

### 5.1 Connection attempts before the server was running
The phone sent repeated `[TCP Retransmission] ... [SYN]` packets to port 8765 and the laptop never answered. This is what a failed connection looks like at the transport layer: the SYN is retried at growing intervals until the server is reachable.

### 5.2 TCP three-way handshake (transport layer)
Packets 7350, 7351 and 7355: the phone sends `[SYN]`, the laptop replies `[SYN, ACK]`, the phone completes with `[ACK]`. Chat messages travel over a reliable, ordered TCP connection. See `01_handshake_and_upgrade.png`.

### 5.3 HTTP upgrade to WebSocket (application layer)
Packet 7356 is an HTTP `GET /` from the phone and packet 7357 is the reply `HTTP/1.1 101 Switching Protocols`. After this the same TCP connection carries WebSocket frames. See `01_handshake_and_upgrade.png`.

### 5.4 Messages are visible in plain text
The first frame from the phone (packet 7361) decodes to:
```
{"type":"hello","name":"jana1","last_id":0}
```
Anyone capturing traffic on the same Wi-Fi can read the name and the message text. No encryption is used on this connection. See `message_plaintext.png`.

The `last_id` field is how the client asks for missed messages. `0` means "send me everything"; the server answers with the stored history right after the hello (the large packets after packet 7362), so a reconnecting client only needs to send the last message ID it saw.

### 5.5 Keep-alive and closing
The server sends a WebSocket `Ping` roughly every 20 seconds and the phone answers with `Pong`. When the page is closed the phone sends a TCP `RST`. See `02_pingpong_and_close.png`.

## 6. Performance tests

Latency, WebSocket vs TCP comparison and scalability tests are in `tests/benchmark.py`, with results in `tests/results/`. They were run on the laptop itself (`localhost`), so they measure server processing, not Wi-Fi.

Note: the capture file `websocket_phone.pcapng` is not committed because it contains unrelated traffic from the laptop. It can be shown during the assessment.
