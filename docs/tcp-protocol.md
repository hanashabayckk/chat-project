## Raw TCP protocol and server metrics (Student 3)

### Application layer: custom TCP text protocol (port 9000)
- Every message is one text line ending in `\n`, with fields separated by `|`.
- Client to server: `HELLO|name|last_id` (join) and `MSG|text` (chat).
- Server to client: `MSG|id|sender|text` (chat) and `ERR|reason` (error).
- `last_id` is the last message ID the client has seen. The server replays every saved message with a higher ID, so reconnecting clients catch up without loss or duplicates.

### Transport layer: framing and validation
- TCP is a byte stream with no message boundaries, so `\n` marks where a message ends and the server reads with `readline()`.
- Text is split with a maximum number of splits, so `|` can appear inside a message.
- Names must be 1 to 20 characters. Messages over 500 characters are rejected with `ERR|message too long`.
- An invalid name gets `ERR|invalid name` and only that client is disconnected.
- A `finally` block removes a closed or crashed client from the broadcast list, so other clients are unaffected.

### Server metrics (`metrics.py`, shown at `/stats`)
- Active and total connections, plus separate WebSocket and TCP client counts.
- Messages handled, bytes in and out, messages per second over the last 10 seconds, and uptime.

### Performance: message overhead (measured with `tests/overhead.py`)
- WebSocket + JSON: 38.0 bytes in and 92.6 bytes out per message.
- Raw TCP: 16.0 bytes in and 25.1 bytes out per message.
- Raw TCP is smaller because JSON repeats field names (`type`, `sender`, `text`, `ts`) in every message. Counts are payload bytes only, without TCP/IP or WebSocket headers.