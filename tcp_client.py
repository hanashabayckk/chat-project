"""Terminal client for the custom TCP protocol.  Usage: python tcp_client.py <server-ip> <name>"""
import asyncio, sys

async def main(host, name):
    reader, writer = await asyncio.open_connection(host, 9000)
    writer.write(f"HELLO|{name}|0\n".encode())

    # a function that runs alongside your typing for messages incomig to arrive while you type
    async def receive():

        # waits for the next line from server and stops when connection is closed
        while line := await reader.readline():

            # turns bytes to text, removes the new lines and splits at most 3
            parts = line.decode().rstrip("\n").split("|", 3)

            if parts[0] == "MSG":
                # message is printed as ( sender id : text)
                print(f"[{parts[1]}] {parts[2]}: {parts[3]}")

            # to cover anything that isn't normal chat message, prints it as it is 
            else:
                print("Server says:", line.decode().strip())
    asyncio.create_task(receive())
    loop = asyncio.get_running_loop()
    while True:
        text = await loop.run_in_executor(None, sys.stdin.readline)
        writer.write(f"MSG|{text.strip()}\n".encode())

asyncio.run(main(sys.argv[1], sys.argv[2]))
