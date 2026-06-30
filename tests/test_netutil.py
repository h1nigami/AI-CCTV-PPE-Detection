"""Тесты сетевых утилит (офлайн-устойчивость): netutil.

Сетевые вызовы замоканы — тесты детерминированы и не ходят в сеть.
"""
import socket
import sys
import types

import backend.netutil as nu


def test_is_private_ipv4():
    assert nu.is_private_ipv4("192.168.1.10")
    assert nu.is_private_ipv4("10.0.0.5")
    assert nu.is_private_ipv4("172.16.5.4")
    assert not nu.is_private_ipv4("8.8.8.8")       # публичный
    assert not nu.is_private_ipv4("127.0.0.1")     # loopback
    assert not nu.is_private_ipv4("169.254.1.1")   # link-local
    assert not nu.is_private_ipv4("not-an-ip")
    assert not nu.is_private_ipv4("::1")           # не IPv4


def _fake_psutil(addrs_by_iface):
    snic = lambda fam, addr: types.SimpleNamespace(family=fam, address=addr)
    return types.SimpleNamespace(
        net_if_addrs=lambda: {
            iface: [snic(fam, addr) for fam, addr in lst]
            for iface, lst in addrs_by_iface.items()
        }
    )


def test_lan_ipv4s_enumerates_interfaces_offline(monkeypatch):
    # Офлайн: маршрута по умолчанию нет → connect-трюк даёт None, но интерфейсы
    # всё равно перечисляются (это и есть фикс для LAN без интернета).
    monkeypatch.setattr(nu, "_connect_trick_ip", lambda: None)
    monkeypatch.setitem(sys.modules, "psutil", _fake_psutil({
        "lo": [(socket.AF_INET, "127.0.0.1")],
        "eth0": [(socket.AF_INET, "192.168.0.42")],
        "wlan0": [(socket.AF_INET, "10.0.0.7")],
    }))
    ips = nu.lan_ipv4s()
    assert "192.168.0.42" in ips
    assert "10.0.0.7" in ips
    assert "127.0.0.1" not in ips   # loopback отброшен


def test_lan_ipv4s_connect_trick_first_and_dedup(monkeypatch):
    monkeypatch.setattr(nu, "_connect_trick_ip", lambda: "192.168.0.42")
    monkeypatch.setitem(sys.modules, "psutil", _fake_psutil({
        "eth0": [(socket.AF_INET, "192.168.0.42")],  # дубль connect-трюка
        "eth1": [(socket.AF_INET, "192.168.5.9")],
    }))
    ips = nu.lan_ipv4s()
    assert ips[0] == "192.168.0.42"          # основной интерфейс первым
    assert ips.count("192.168.0.42") == 1    # без дублей
    assert "192.168.5.9" in ips


def test_is_online_false_when_unreachable(monkeypatch):
    def boom(*a, **k):
        raise OSError("no route to host")
    monkeypatch.setattr(nu.socket, "create_connection", boom)
    assert nu.is_online(timeout=0.05) is False


def test_is_online_true_when_reachable(monkeypatch):
    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(nu.socket, "create_connection", lambda *a, **k: FakeConn())
    assert nu.is_online() is True


def test_scan_prefixes_uses_lan_ips_offline(monkeypatch):
    # discovery.scan_prefixes должен брать подсети локальных интерфейсов даже без
    # явного DISCOVERY_SUBNET и без known-камер (офлайн-сценарий LAN).
    import backend.discovery as disc
    monkeypatch.setattr(nu, "lan_ipv4s", lambda: ["192.168.0.42", "10.0.0.7"])
    prefixes = disc.scan_prefixes(extra_subnets=None, known_ips=None)
    assert "192.168.0" in prefixes
    assert "10.0.0" in prefixes
