"""Сетевые утилиты: локальные LAN-адреса и быстрая проверка интернета.

Главная цель — корректная работа БЕЗ интернета:

  • ``lan_ipv4s()`` — все приватные IPv4 хоста на всех интерфейсах. Старый приём
    ``connect(("8.8.8.8", 80))`` для определения своего адреса ПАДАЕТ, если нет
    маршрута по умолчанию (LAN без выхода в интернет), и тогда сканировать
    подсеть камер не из чего. Перечисление интерфейсов через psutil даёт LAN-адрес
    даже офлайн.

  • ``is_online()`` — быстрый TCP-коннект к публичным DNS с коротким таймаутом.
    Нужен, чтобы офлайн-старт НЕ висел на сетевых ретраях скачивания моделей
    (InsightFace/OSNet/Piper): нет сети → сразу мягкая деградация, без задержек.

Без обязательных зависимостей: psutil уже в requirements (метрики), при его
отсутствии есть фоллбэк на ``socket.getaddrinfo`` по hostname.
"""
from __future__ import annotations
import ipaddress
import socket
from typing import List


def is_private_ipv4(ip: str) -> bool:
    """True для приватного (RFC1918) IPv4, кроме loopback/link-local."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return (addr.version == 4 and addr.is_private
            and not addr.is_loopback and not addr.is_link_local)


def _connect_trick_ip() -> str | None:
    """IP исходящего интерфейса через UDP-connect (данные не шлются). Возвращает
    None, если нет маршрута по умолчанию (типично для LAN без интернета)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return None
    finally:
        s.close()


def lan_ipv4s() -> List[str]:
    """Все приватные IPv4-адреса хоста (на всех интерфейсах), дедуплицированные.

    Порядок: сначала адрес основного интерфейса (connect-трюк, когда есть
    маршрут), затем адреса всех интерфейсов из psutil. Работает офлайн —
    в отличие от одного connect-трюка, который без маршрута по умолчанию даёт
    None. Loopback/link-local отброшены."""
    ips: List[str] = []
    seen: set[str] = set()

    def add(ip: str | None):
        if ip and ip not in seen and is_private_ipv4(ip):
            seen.add(ip)
            ips.append(ip)

    add(_connect_trick_ip())
    try:
        import psutil
        for addrs in psutil.net_if_addrs().values():
            for a in addrs:
                if a.family == socket.AF_INET:
                    add(a.address)
    except Exception:
        # psutil недоступен — хотя бы по hostname (на Linux часто 127.0.1.1,
        # тогда ничего приватного не добавится — это ок).
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None,
                                           socket.AF_INET):
                add(info[4][0])
        except Exception:
            pass
    return ips


def is_online(timeout: float = 1.5,
              hosts=(("8.8.8.8", 53), ("1.1.1.1", 53))) -> bool:
    """Быстрая проверка интернета: TCP-коннект к публичным DNS (порт 53) с
    коротким таймаутом. Офлайн → False быстро, без долгих сетевых зависаний."""
    for host, port in hosts:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            continue
    return False
