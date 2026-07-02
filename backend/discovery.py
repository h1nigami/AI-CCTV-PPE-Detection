"""Автообнаружение RTSP-камер в локальной сети.

Два метода (см. discover_streams):
  1. ONVIF WS-Discovery — multicast-проба (UDP 3702), камеры сами отвечают
     своими адресами. Надёжно, если камера поддерживает ONVIF (большинство).
     Probe шлётся дважды (UDP теряется), ответы собираются весь таймаут.
  2. Фоллбэк — скан локальной подсети: открытые порты 554 + перебор типовых
     RTSP-путей вендоров.

Скан двухфазный: (1) быстрый широкий TCP-скан порта 554 по всем адресам,
(2) классификация только откликнувшихся хостов. Пути проверяются лёгким
запросом RTSP DESCRIBE (миллисекунды на путь, не занимает RTSP-сессию камеры):
200 — путь открыт без пароля, 401/407 — камера запаролена, 404 — нет такого
пути. Полное открытие потока ffmpeg'ом (`probe_rtsp`) — только страховочный
фоллбэк для хостов, не отвечающих на DESCRIBE, и финальная проверка при
добавлении запароленной камеры с кредами.

ВНИМАНИЕ (Docker): WS-Discovery — multicast, в bridge-сети не проходит, для
ONVIF контейнеру бэка нужен `network_mode: host`. А вот СКАН подсети из bridge
работает (исходящий TCP на LAN проходит через docker SNAT) — нужно лишь
сканировать правильную подсеть, а не docker-сеть, которую отдаёт `local_ip()`.
Поэтому подсеть для скана задаётся явно (env DISCOVERY_SUBNET) и/или выводится
из IP уже добавленных камер (`scan_prefixes`). Только для СВОЕЙ локальной сети.

Сетевые операции изолированы; чистые помощники (parsing/url-building/подсеть)
тестируются без сети.
"""
from __future__ import annotations
import re
import socket
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

# Типовые RTSP-пути основных вендоров (channel 1 / main или sub-stream).
COMMON_RTSP_PATHS = [
    "/stream1",                           # частый OEM (то, что используем мы)
    "/Streaming/Channels/101",            # Hikvision main
    "/Streaming/Channels/102",            # Hikvision sub
    "/cam/realmonitor?channel=1&subtype=0",  # Dahua main
    "/cam/realmonitor?channel=1&subtype=1",  # Dahua sub
    "/h264Preview_01_main",               # Reolink
    "/live/ch00_0",                       # многие OEM
    "/live/main",
    "/live.sdp",
    "/11",
    "/video1",
    "/onvif1",
    "/ch0_0.h264",
    "/",
]

_WS_DISCOVERY_ADDR = ("239.255.255.250", 3702)

# Таймауты и лимиты сканирования.
PORT_TIMEOUT = 1.0      # с; TCP-коннект к 554 — на WiFi пики латентности > 0.4с
PORT_RETRIES = 1        # повтор при неответе (потерянный SYN на WiFi = «через раз»)
DESCRIBE_TIMEOUT = 1.5  # с; ответ камеры на RTSP DESCRIBE
DESCRIBE_MAX_SILENT = 3  # порт 554 открыт, но N путей подряд без RTSP-ответа → не RTSP
PORT_SCAN_WORKERS = 128  # фаза 1 — лёгкие TCP-коннекты, можно широко


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


def prefix_of(ip: str) -> str | None:
    """/24-префикс (первые три октета) IPv4-адреса. None для мусора."""
    parts = ip.split(".")
    if len(parts) < 3 or not all(p.isdigit() for p in parts[:3]):
        return None
    return ".".join(parts[:3])


def ips_from_sources(sources) -> set[str]:
    """IPv4-адреса из источников камер (RTSP-URL и т.п.). int-камеры игнорируются."""
    ips: set[str] = set()
    for src in sources:
        if not isinstance(src, str):
            continue
        for ip in re.findall(r"(?<![\d.])((?:\d{1,3}\.){3}\d{1,3})(?![\d.])", src):
            ips.add(ip)
    return ips


def paths_from_sources(sources) -> list[str]:
    """RTSP-пути (с query) из источников камер — чтобы пробовать их при скане
    первыми. 'rtsp://1.2.3.4:554/stream1?x=1' → '/stream1?x=1'. Порядок и
    уникальность сохраняются (первое вхождение)."""
    paths: list[str] = []
    seen: set[str] = set()
    for src in sources:
        if not isinstance(src, str):
            continue
        host_and_path = re.sub(r"^\w+://", "", src.strip())  # срезать схему (rtsp://)
        idx = host_and_path.find("/")                        # путь = от первого '/'
        if idx == -1:
            continue
        path = host_and_path[idx:]
        if path and path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def merge_paths(known: list[str], common: list[str] = None) -> list[str]:
    """Пути для перебора: сначала пути известных камер, затем типовые (без дублей)."""
    common = common if common is not None else COMMON_RTSP_PATHS
    out: list[str] = []
    seen: set[str] = set()
    for p in list(known) + list(common):
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def normalize_subnets(values) -> set[str]:
    """Нормализовать список подсетей/IP/CIDR в множество /24-префиксов 'a.b.c'.

    Принимает 'a.b.c', 'a.b.c.d', 'a.b.c.d/24', 'a.b.c.0/24' — из всего берёт
    первые три октета. Мусор тихо отбрасывается."""
    prefixes: set[str] = set()
    for v in values:
        if not isinstance(v, str):
            continue
        token = v.strip().split("/", 1)[0]  # отбросить маску CIDR
        if not token:
            continue
        p = prefix_of(token)
        if p:
            prefixes.add(p)
    return prefixes


def hosts_for_prefixes(prefixes) -> set[str]:
    """Все хосты .1..254 для набора /24-префиксов."""
    hosts: set[str] = set()
    for prefix in prefixes:
        hosts |= {f"{prefix}.{i}" for i in range(1, 255)}
    return hosts


def name_for_ip(ip: str) -> str:
    return "cam_" + ip.replace(".", "_")


def auth_candidate_urls(ip: str, username: str, password: str, port: int = 554,
                        paths: list[str] = None) -> list[str]:
    """RTSP-URL с логином/паролем для перебора путей. Логин и пароль
    URL-кодируются (могут содержать '@', ':', '/' и др. спецсимволы — иначе URL
    разберётся неверно). Без логина/пароля кредов в URL нет."""
    from urllib.parse import quote
    paths = paths if paths is not None else COMMON_RTSP_PATHS
    cred = ""
    if username or password:
        cred = f"{quote(username or '', safe='')}:{quote(password or '', safe='')}@"
    return [f"rtsp://{cred}{ip}:{port}{p}" for p in paths]


def parse_rtsp_status(data: bytes) -> int | None:
    """Код из статус-строки RTSP-ответа ('RTSP/1.0 200 OK' → 200). None — мусор."""
    m = re.match(rb"RTSP/\d\.\d\s+(\d{3})", data or b"")
    return int(m.group(1)) if m else None


def prioritize_paths(paths: list[str], statuses: dict) -> list[str]:
    """Порядок перебора путей с кредами по итогам DESCRIBE без кредов:
    пути, ответившие 200/401/407 (существуют на камере), — первыми; молчавшие
    (None) — потом; 404 и прочие — в конец (404 без кредов останется 404 и с
    ними). Внутри групп исходный порядок сохраняется (sorted стабильна)."""
    def rank(p):
        code = statuses.get(p)
        if code in (200, 401, 407):
            return 0
        if code is None:
            return 1
        return 2
    return sorted(paths, key=rank)


# ── Сетевые операции ────────────────────────────────────────────────────────
def local_ip() -> str | None:
    """Основной локальный LAN-адрес хоста (или None). Работает офлайн: берётся
    первый приватный IPv4 из перечисления интерфейсов (см. netutil.lan_ipv4s),
    а не только connect-трюк, который без маршрута по умолчанию даёт None."""
    from backend.netutil import lan_ipv4s
    ips = lan_ipv4s()
    return ips[0] if ips else None


def discover_onvif(timeout: float = 3.0) -> set[str]:
    """WS-Discovery multicast-проба. Возвращает множество IP найденных устройств.

    Probe шлётся дважды (в начале и на середине окна) — одиночный UDP-пакет
    теряется, и камеры «находились через раз». Ответы собираются ВЕСЬ таймаут
    короткими recv-слотами (раньше первый же recv-таймаут обрывал сбор)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    payloads: list[str] = []
    try:
        sock.sendto(_probe_message(), _WS_DISCOVERY_ADDR)
        deadline = time.time() + timeout
        resend_at = time.time() + timeout / 2
        while True:
            now = time.time()
            if now >= deadline:
                break
            if now >= resend_at:
                try:
                    sock.sendto(_probe_message(), _WS_DISCOVERY_ADDR)
                except Exception:
                    pass
                resend_at = float("inf")
            sock.settimeout(min(0.5, deadline - now))
            try:
                data, _ = sock.recvfrom(65535)
                payloads.append(data.decode("utf-8", errors="replace"))
            except socket.timeout:
                continue
            except Exception:
                break
    except Exception as exc:
        print(f"[Discovery] WS-Discovery недоступен: {exc}")
    finally:
        sock.close()
    return ips_from_ws_responses(payloads)


def _port_open(ip: str, port: int = 554, timeout: float = PORT_TIMEOUT,
               retries: int = PORT_RETRIES) -> bool:
    for _ in range(retries + 1):
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return True
        except Exception:
            continue
    return False


def rtsp_describe_status(ip: str, path: str, port: int = 554,
                         timeout: float = DESCRIBE_TIMEOUT) -> int | None:
    """Лёгкая проверка RTSP-пути запросом DESCRIBE (без открытия потока и
    декодера): 200 — путь открыт без пароля, 401/407 — нужен логин, 404/454 —
    нет такого пути, None — хост не ответил как RTSP-сервер. Миллисекунды
    против секунд полного открытия ffmpeg'ом; не занимает RTSP-сессию камеры
    (у камер лимит одновременных подключений — тяжёлая проба при живом стриме
    отклонялась, и камера «находилась через раз»)."""
    req = (f"DESCRIBE rtsp://{ip}:{port}{path} RTSP/1.0\r\n"
           "CSeq: 1\r\nAccept: application/sdp\r\nUser-Agent: ppe-discovery\r\n\r\n")
    try:
        with socket.create_connection((ip, port), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall(req.encode("utf-8"))
            data = b""
            while b"\r\n" not in data and len(data) < 4096:
                chunk = s.recv(2048)
                if not chunk:
                    break
                data += chunk
            return parse_rtsp_status(data)
    except Exception:
        return None


def describe_paths(ip: str, paths: list[str], port: int = 554):
    """Прогнать DESCRIBE по путям. Возвращает (первый путь с 200 | None,
    встречался_ли_401/407, отвечал_ли_хост_как_RTSP). Ранний выход на первом
    200; если первые DESCRIBE_MAX_SILENT путей молчат и ответов не было вовсе —
    хост не RTSP-сервер, дальше не перебираем."""
    saw_auth = False
    responded = False
    for i, p in enumerate(paths):
        code = rtsp_describe_status(ip, p, port)
        if code is not None:
            responded = True
            if code == 200:
                return p, saw_auth, True
            if code in (401, 407):
                saw_auth = True
        elif not responded and i + 1 >= DESCRIBE_MAX_SILENT:
            break
    return None, saw_auth, responded


def probe_rtsp(url: str, timeout_ms: int = 2500) -> bool:
    """Полное открытие потока (ffmpeg) + чтение кадра. Таймауты передаются
    В КОНСТРУКТОР VideoCapture: он блокируется на открытии ещё в конструкторе,
    и `cap.set(CAP_PROP_OPEN_TIMEOUT_MSEC)` после создания уже не действует —
    проба висела на дефолтном таймауте ffmpeg (десятки секунд на путь), из-за
    чего поиск камер работал минутами."""
    import cv2
    params = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms,
              cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms]
    try:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, params)
    except TypeError:  # старый OpenCV без params-конструктора
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    try:
        if not cap.isOpened():
            return False
        ok, frame = cap.read()
        return bool(ok and frame is not None)
    finally:
        cap.release()


def probe_rtsp_auth(ip: str, username: str, password: str, port: int = 554,
                    paths: list[str] = None) -> str | None:
    """Перебрать типовые RTSP-пути С логином/паролем; вернуть первый рабочий URL
    или None. Используется для запароленных камер (поток без логина не открылся).

    Перед тяжёлым перебором пути классифицируются лёгким DESCRIBE без кредов:
    существующие на камере (ответ 200/401) пробуются первыми, 404 — последними.
    Иначе до нужного пути перебирались чужие вендорские по ~2.5с каждый."""
    paths = list(paths if paths is not None else COMMON_RTSP_PATHS)
    statuses: dict = {}
    for i, p in enumerate(paths):
        code = rtsp_describe_status(ip, p, port)
        statuses[p] = code
        if code is None and i + 1 >= DESCRIBE_MAX_SILENT \
                and all(v is None for v in statuses.values()):
            break  # хост не отвечает на DESCRIBE — классификация бессмысленна
    for url in auth_candidate_urls(ip, username, password, port,
                                   prioritize_paths(paths, statuses)):
        if probe_rtsp(url):
            return url
    return None


def _probe_host(ip: str, paths: list[str] = None, onvif_ips=None,
                port_open: bool | None = None) -> dict | None:
    """Статус хоста как камеры:
      • открытая  — какой-то путь ответил 200 на DESCRIBE без логина
        (`requires_auth=False`, есть rtsp_url);
      • запароленная — порт 554 открыт ИЛИ ответил ONVIF, но открытого пути
        нет (`requires_auth=True`, rtsp_url=None) → UI предложит логин/пароль;
      • не камера — None.
    `port_open` можно передать готовым (фаза 1 скана уже проверила порт)."""
    is_onvif = bool(onvif_ips and ip in onvif_ips)
    if port_open is None:
        port_open = _port_open(ip)
    if not port_open and not is_onvif:
        return None
    paths = paths if paths is not None else COMMON_RTSP_PATHS
    rtsp_url = None
    if port_open:
        open_path, saw_auth, responded = describe_paths(ip, paths)
        if open_path:
            rtsp_url = candidate_urls(ip, paths=[open_path])[0]
        elif not responded:
            # Порт 554 открыт, но на DESCRIBE хост не ответил (нестандартный
            # RTSP-сервер) — страховка: полное открытие первых путей ffmpeg'ом
            # с жёстким таймаутом.
            for url in candidate_urls(ip, paths=paths[:4]):
                if probe_rtsp(url):
                    rtsp_url = url
                    break
    if rtsp_url:
        return {"ip": ip, "rtsp_url": rtsp_url, "name": name_for_ip(ip),
                "requires_auth": False, "port": 554}
    return {"ip": ip, "rtsp_url": None, "name": name_for_ip(ip),
            "requires_auth": True, "port": 554}


def scan_prefixes(extra_subnets=None, known_ips=None) -> set[str]:
    """/24-префиксы для скана: явные подсети + подсети известных камер + локальная.

    В Docker bridge `local_ip()` возвращает адрес docker-сети (172.x), поэтому
    одного его мало — отсюда явные `extra_subnets` (env DISCOVERY_SUBNET) и
    автоинференс подсети по IP уже добавленных камер."""
    prefixes: set[str] = set()
    if extra_subnets:
        prefixes |= normalize_subnets(extra_subnets)
    if known_ips:
        prefixes |= {p for p in (prefix_of(ip) for ip in known_ips) if p}
    # Подсети ВСЕХ локальных интерфейсов (работает офлайн, ловит несколько LAN).
    from backend.netutil import lan_ipv4s
    for ip in lan_ipv4s():
        p = prefix_of(ip)
        if p:
            prefixes.add(p)
    return prefixes


def discover_streams(use_onvif: bool = True, use_scan: bool = True,
                     onvif_timeout: float = 3.0, max_workers: int = 32,
                     extra_subnets=None, known_ips=None, known_paths=None) -> list[dict]:
    """Найти открытые RTSP-потоки в локальной сети.

    Возвращает список {ip, rtsp_url, name, requires_auth, port}. Двухфазно:
      1. Быстрый широкий TCP-скан порта 554 по всем адресам (ONVIF + подсети) —
         лёгкие коннекты, пул PORT_SCAN_WORKERS.
      2. Классификация ТОЛЬКО откликнувшихся хостов (DESCRIBE по путям).
    Раньше обе фазы были слиты в один пул, а каждый путь проверялся полным
    открытием потока — весь скан упирался в тяжёлые пробы и работал минутами.

    `extra_subnets` — явные подсети для скана (env DISCOVERY_SUBNET), `known_ips`
    — IP уже добавленных камер (для автоинференса нужной подсети в Docker, где
    `local_ip()` указывает на docker-bridge, а не на LAN с камерами). `known_paths`
    — RTSP-пути уже добавленных камер (например `/stream1`): пробуются первыми."""
    ips: set[str] = set()
    onvif_ips: set[str] = set()
    if use_onvif:
        onvif_ips = discover_onvif(onvif_timeout)
        ips |= onvif_ips
        print(f"[Discovery] ONVIF нашёл IP: {len(onvif_ips)}")
    if use_scan:
        prefixes = scan_prefixes(extra_subnets, known_ips)
        scan_ips = hosts_for_prefixes(prefixes)
        ips |= scan_ips
        print(f"[Discovery] Скан подсетей {sorted(prefixes)} → {len(scan_ips)} адресов")
    if not ips:
        print("[Discovery] Нет адресов для проверки (задайте DISCOVERY_SUBNET).")
        return []
    paths = merge_paths(known_paths or [])
    # Фаза 1: у кого вообще открыт RTSP-порт (лёгкий TCP-коннект, широкий пул).
    ip_list = sorted(ips)
    with ThreadPoolExecutor(max_workers=min(PORT_SCAN_WORKERS, len(ip_list))) as pool:
        open_map = dict(zip(ip_list, pool.map(_port_open, ip_list)))
    candidates = [ip for ip in ip_list if open_map[ip] or ip in onvif_ips]
    print(f"[Discovery] Кандидатов (порт 554 / ONVIF): {len(candidates)}")
    # Фаза 2: классификация кандидатов (открытая / запароленная).
    found: list[dict] = []
    if candidates:
        classify = lambda ip: _probe_host(ip, paths, onvif_ips, open_map[ip])
        with ThreadPoolExecutor(max_workers=min(max_workers, len(candidates))) as pool:
            found = [res for res in pool.map(classify, candidates) if res]
    # Открытые камеры — первыми, затем запароленные; внутри — по IP.
    found.sort(key=lambda d: (d["requires_auth"], d["ip"]))
    n_open = sum(1 for f in found if not f["requires_auth"])
    print(f"[Discovery] Найдено камер: {len(found)} "
          f"(открытых {n_open}, под паролем {len(found) - n_open})")
    return found
