"""Package for web servers the engine may need to start."""

import socket


def bind_free_socket(host: str, port: int) -> socket.socket:
    """Bind a TCP socket to the given host and port and return it.

    When port is 0 the OS assigns a free port automatically. When a
    non-zero port is requested but already in use, the function falls
    back to port 0 so the OS assigns a free port. The caller can read
    the actual port via ``sock.getsockname()[1]`` and must eventually
    close the socket.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError:
        sock.bind((host, 0))
    return sock
