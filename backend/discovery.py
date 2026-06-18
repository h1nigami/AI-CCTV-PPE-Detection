"""Автообнаружение RTSP-камер в локальной сети.

Два метода (см. discover_streams):
  1. ONVIF WS-Discovery — multicast-проба (UDP 3702), камеры сами отвечают
     своими адресами. Надёжно, если камера поддерживает ONVIF (большинство).
  2. Фоллбэк — скан локальной подсети: открытые порты 554 + перебор типовых
     RTSP-путей вендоров.

«Непаролёность» проверяется фактическим открытием потока без учётных данных
(`probe_rtsp` через OpenCV/ffmpeg): открылся и отдал кадр → камера открытая.

ВНИМАНИЕ (Docker): WS-Discovery — multicast, в bridge-сети не проходит. Для
обнаружения в LAN контейнеру бэка нужен `network_mode: host` (или скан подсети
хоста). Только для СВОЕЙ локальной сети.

Сетевые операции изолированы; чистые помощники (parsing/url-building/подсеть)
тестируются без сети.
"""
from __future__ import annotations
import re
import socket
import uuid
from concurrent.futures import ThreadPoolExecutor

# Типовые RTSP-пути основных вендоров (channel 1 / main или sub-stream).
COMMON_RTSP_PATHS = [
    "/Streaming/Channels/101",            # Hikvision main
    "/Streaming/Channels/102",            # Hikvision sub
    "/cam/realmonitor?channel=1&subtype=0",  # Dahua main
    "/cam/realmonitor?channel=1&subtype=1",  # Dahua sub
    "/h264Preview_01_main",               # Reolink
    "/live/ch00_0",                       # многие OEM
    "/live/main",
    "/live.sdp",
    "/11",
    "/stream1",
    "/video1",
    "/onvif1",
    "/ch0_0.h264",
    "/",
]

_WS_DISCOVERY_ADDR = ("239.255.255.250", 3702)


def _probe_message() -> bytes:
    """SOAP-конверт WS-Discovery Probe для NetworkVideoTransmitter (ONVIF)."""
    msg_id = uuid.uuid4()
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
        'xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
        'xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
        '<e:Header>'
        f'<w:MessageID>uuid:{msg_id}</w:MessageID>'
        '<w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>'
        '<w:Action e:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>'
        '</e:Header>'
        '<e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body>'
        '</e:Envelope>'
    ).encode("utf-8")


# ── Чистые помощники (без сети) ─────────────────────────────────────────────
def ips_from_ws_responses(payloads: list[str]) -> set[str]:
    """Извлечь IP-адреса камер из XAddrs в ответах WS-Discovery."""
    ips: set[str] = set()
    for payload in payloads:
        for url in re.findall(r"https?://([0-9.]+)(?::\d+)?", payload):
            ips.add(url)
    return ips


def candidate_urls(ip: str, port: int = 554, paths: list[str] = None) -> list[str]:
    paths = paths if paths is not None else COMMON_RTSP_PATHS
    return [f"rtsp://{ip}:{port}{p}" for p in paths]


def subnet_hosts(base_ip: str) -> list[str]:
    """Все адреса /24-подсети для base_ip (без .0 и .255)."""
    parts = base_ip.split(".")
    if len(parts) != 4:
        return []
    prefix = ".".join(parts[:3])
    return [f"{prefix}.{i}" for i in range(1, 255)]


def name_for_ip(ip: str) -> str:
    return "cam_" + ip.replace(".", "_")


# ── Сетевые операции ────────────────────────────────────────────────────────
def local_ip() -> str | None:
    """IP-адрес хоста в локальной сети (через UDP-сокет, без отправки данных)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return None
    finally:
        s.close()


def discover_onvif(timeout: float = 3.0) -> set[str]:
    """WS-Discovery multicast-проба. Возвращает множество IP найденных устройств."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(timeout)
    payloads: list[str] = []
    try:
        sock.sendto(_probe_message(), _WS_DISCOVERY_ADDR)
        import time as _t
        deadline = _t.time() + timeout
        while _t.time() < deadline:
            try:
                data, _ = sock.recvfrom(65535)
                payloads.append(data.decode("utf-8", errors="replace"))
            except socket.timeout:
                break
            except Exception:
                break
    except Exception as exc:
        print(f"[Discovery] WS-Discovery недоступен: {exc}")
    finally:
        sock.close()
    return ips_from_ws_responses(payloads)


def _port_open(ip: str, port: int = 554, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def probe_rtsp(url: str, timeout_ms: int = 4000) -> bool:
    """Открывается ли поток БЕЗ учётных данных (т.е. камера «непаролёная»)."""
    import cv2
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    try:
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms)
    except Exception:
        pass
    try:
        if not cap.isOpened():
            return False
        ok, frame = cap.read()
        return bool(ok and frame is not None)
    finally:
        cap.release()


def _first_open_url(ip: str) -> str | None:
    if not _port_open(ip):
        return None
    for url in candidate_urls(ip):
        if probe_rtsp(url):
            return url
    return None


def discover_streams(use_onvif: bool = True, use_scan: bool = True,
                     onvif_timeout: float = 3.0, max_workers: int = 32) -> list[dict]:
    """Найти открытые RTSP-потоки в локальной сети.

    Возвращает список {ip, rtsp_url, name}. Сначала собирает IP (ONVIF + скан
    подсети), затем параллельно проверяет открытость потока без пароля."""
    ips: set[str] = set()
    if use_onvif:
        ips |= discover_onvif(onvif_timeout)
    if use_scan:
        base = local_ip()
        if base:
            ips |= set(subnet_hosts(base))
    if not ips:
        return []
    found: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for ip, url in zip(ips, pool.map(_first_open_url, ips)):
            if url:
                found.append({"ip": ip, "rtsp_url": url, "name": name_for_ip(ip)})
    found.sort(key=lambda d: d["ip"])
    return found
