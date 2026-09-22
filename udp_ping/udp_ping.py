import socket
import sys

TARGET_HOST = "127.0.0.1"
TARGET_PORT = 30015
MESSAGE = "ping"
TIMEOUT = 5.0
BUFFER_SIZE = 4096


def main() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(TIMEOUT)

        try:
            sock.sendto(MESSAGE.encode("utf-8"), (TARGET_HOST, TARGET_PORT))
            print(f"Sent: {MESSAGE!r} -> {TARGET_HOST}:{TARGET_PORT}")
        except OSError as exc:
            print(f"Send failed: {exc}", file=sys.stderr)
            return 1

        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
        except socket.timeout:
            print("No reply received (timeout).", file=sys.stderr)
            return 2

        text = data.decode("utf-8", errors="replace")
        print(f"Received from {addr[0]}:{addr[1]}: {text!r}")
        return 0


if __name__ == "__main__":
    sys.exit(main())