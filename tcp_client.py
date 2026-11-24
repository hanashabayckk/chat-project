"""Terminal client for the custom TCP protocol.  Usage: python tcp_client.py <server-ip> <name>"""
import asyncio, sys

async def main(host, name):
    reader, writer = await asyncio.open_connection(host, 9000)
    writer.write(f"HELLO|{name}|0\n".encode())
    async def receive():
        while line := await reader.readline():
            _, mid, sender, text = line.decode().rstrip("\n").split("|", 3)
            print(f"[{mid}] {sender}: {text}")
    asyncio.create_task(receive())
    loop = asyncio.get_running_loop()
    while True:
        text = await loop.run_in_executor(None, sys.stdin.readline)
        writer.write(f"MSG|{text.strip()}\n".encode())

asyncio.run(main(sys.argv[1], sys.argv[2]))
