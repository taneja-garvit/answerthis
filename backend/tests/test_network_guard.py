import socket

import httpx
import pytest


async def test_real_http_is_blocked():
    async with httpx.AsyncClient() as client:
        with pytest.raises(RuntimeError, match="disabled in tests"):
            await client.get("https://api.crossref.org/works/10.1002/ejhf.3568")


def test_raw_sockets_and_dns_are_blocked():
    with pytest.raises(RuntimeError, match="DNS lookup attempted"):
        socket.getaddrinfo("api.groq.com", 443)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        with pytest.raises(RuntimeError, match="Network access attempted"):
            sock.connect(("1.1.1.1", 443))
