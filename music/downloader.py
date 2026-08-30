import os
from urllib.parse import urlparse

import requests
import socks
from radiojavanapi import Client as RJClient


DOWNLOAD_DIR = os.path.join(
    os.getenv("DATA_DIR", "/data"),
    "downloads",
)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

_rj = RJClient()


def _get_proxy_url():
    return os.getenv("SOCKS5_PROXY_URL", "").strip() or None


def _cache_path(song_id) -> str:
    return os.path.join(DOWNLOAD_DIR, f"rj_{song_id}.m4a")


def _download_via_socks5(url: str, destination: str):
    """
    Download a RadioJavan media file through the configured SOCKS5 proxy.

    This uses a raw SOCKS5 socket instead of requests' SOCKS adapter,
    because the Liara -> proxy -> RadioJavan CDN path has proven to work
    reliably at the socket/TLS level.
    """
    proxy_url = _get_proxy_url()

    if not proxy_url:
        raise RuntimeError(
            "SOCKS5_PROXY_URL is not configured. "
            "RadioJavan media CDN is unreachable directly from Liara."
        )

    proxy = urlparse(proxy_url)

    if proxy.scheme.lower() not in ("socks5", "socks5h"):
        raise RuntimeError(
            f"Unsupported proxy scheme: {proxy.scheme}. "
            "SOCKS5_PROXY_URL must start with socks5://"
        )

    target = urlparse(url)

    if target.scheme.lower() != "https":
        raise RuntimeError(
            f"Unsupported media URL scheme: {target.scheme}"
        )

    proxy_host = proxy.hostname
    proxy_port = proxy.port

    if not proxy_host or not proxy_port:
        raise RuntimeError("Invalid SOCKS5_PROXY_URL")

    # Connect through SOCKS5.
    sock = socks.socksocket()
    sock.set_proxy(
        socks.SOCKS5,
        proxy_host,
        proxy_port,
        username=proxy.username,
        password=proxy.password,
    )
    sock.settimeout(60)

    try:
        sock.connect((target.hostname, target.port or 443))

        import ssl

        context = ssl.create_default_context()

        with context.wrap_socket(
            sock,
            server_hostname=target.hostname,
        ) as conn:

            path = target.path or "/"

            if target.query:
                path += "?" + target.query

            request = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {target.hostname}\r\n"
                "User-Agent: Mozilla/5.0\r\n"
                "Accept: */*\r\n"
                "Connection: close\r\n"
                "\r\n"
            )

            conn.sendall(request.encode("ascii"))

            # Read HTTP headers.
            buffer = b""

            while b"\r\n\r\n" not in buffer:
                chunk = conn.recv(4096)

                if not chunk:
                    raise RuntimeError(
                        "RadioJavan CDN closed the connection "
                        "before sending HTTP headers."
                    )

                buffer += chunk

                if len(buffer) > 64 * 1024:
                    raise RuntimeError(
                        "HTTP headers are unexpectedly large."
                    )

            header_bytes, body = buffer.split(
                b"\r\n\r\n",
                1,
            )

            headers_text = header_bytes.decode(
                "iso-8859-1",
                errors="replace",
            )

            header_lines = headers_text.split("\r\n")

            status_line = header_lines[0]

            try:
                status_code = int(status_line.split()[1])
            except (IndexError, ValueError):
                raise RuntimeError(
                    f"Invalid HTTP response from RadioJavan: "
                    f"{status_line}"
                )

            if status_code < 200 or status_code >= 300:
                raise RuntimeError(
                    f"RadioJavan CDN returned HTTP {status_code}: "
                    f"{status_line}"
                )

            content_length = None

            for line in header_lines[1:]:
                if ":" not in line:
                    continue

                key, value = line.split(":", 1)

                if key.lower().strip() == "content-length":
                    try:
                        content_length = int(value.strip())
                    except ValueError:
                        pass

            temp_path = destination + ".part"
            total = 0

            try:
                with open(temp_path, "wb") as f:

                    if body:
                        f.write(body)
                        total += len(body)

                    while True:
                        chunk = conn.recv(1024 * 1024)

                        if not chunk:
                            break

                        f.write(chunk)
                        total += len(chunk)

                if content_length is not None and total != content_length:
                    raise RuntimeError(
                        f"Incomplete RadioJavan download: "
                        f"{total}/{content_length} bytes"
                    )

                os.replace(temp_path, destination)

            except Exception:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
                raise

            return total

    finally:
        try:
            sock.close()
        except Exception:
            pass


def search_and_download(query: str) -> dict:
    """
    Search RadioJavan and download the first result.

    Result shape:
    {
        "title": str,
        "duration": int,
        "file_path": str,
        "video_id": str
    }
    """

    results = _rj.search(query)

    if not results.songs:
        return None

    short = results.songs[0]
    song = _rj.get_song_by_id(short.id)

    cached = _cache_path(song.id)

    title = (
        f"{song.artist} - {song.name}"
        if song.artist
        else song.name
    )

    if not os.path.exists(cached):
        link = song.hq_link or song.lq_link

        if not link:
            raise RuntimeError(
                "RadioJavan returned no downloadable media link."
            )

        link = str(link)

        _download_via_socks5(
            link,
            cached,
        )

    return {
        "title": title,
        "duration": song.duration,
        "file_path": cached,
        "video_id": str(song.id),
    }