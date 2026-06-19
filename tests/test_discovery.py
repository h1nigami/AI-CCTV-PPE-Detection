"""Тесты чистых помощников автообнаружения камер (без сети)."""
from backend.discovery import (
    ips_from_ws_responses, candidate_urls, subnet_hosts, name_for_ip,
    prefix_of, ips_from_sources, normalize_subnets, hosts_for_prefixes,
    COMMON_RTSP_PATHS,
)


def test_ips_from_ws_responses():
    payloads = [
        "<XAddrs>http://192.168.1.50:80/onvif/device_service</XAddrs>",
        "blah http://192.168.1.51/onvif http://192.168.1.50:8000/x",  # дубль .50
        "no urls here",
    ]
    ips = ips_from_ws_responses(payloads)
    assert ips == {"192.168.1.50", "192.168.1.51"}


def test_ips_from_ws_responses_empty():
    assert ips_from_ws_responses([]) == set()
    assert ips_from_ws_responses(["nothing"]) == set()


def test_candidate_urls():
    urls = candidate_urls("10.0.0.5")
    assert all(u.startswith("rtsp://10.0.0.5:554") for u in urls)
    assert len(urls) == len(COMMON_RTSP_PATHS)
    assert "rtsp://10.0.0.5:554/Streaming/Channels/101" in urls


def test_candidate_urls_custom_path_and_port():
    urls = candidate_urls("10.0.0.5", port=8554, paths=["/live"])
    assert urls == ["rtsp://10.0.0.5:8554/live"]


def test_subnet_hosts():
    hosts = subnet_hosts("192.168.1.42")
    assert hosts[0] == "192.168.1.1"
    assert hosts[-1] == "192.168.1.254"
    assert len(hosts) == 254
    assert "192.168.1.0" not in hosts and "192.168.1.255" not in hosts


def test_subnet_hosts_bad_input():
    assert subnet_hosts("not-an-ip") == []


def test_name_for_ip():
    assert name_for_ip("192.168.1.50") == "cam_192_168_1_50"


def test_prefix_of():
    assert prefix_of("192.168.0.42") == "192.168.0"
    assert prefix_of("10.0.5") == "10.0.5"      # уже префикс
    assert prefix_of("not-an-ip") is None
    assert prefix_of("") is None


def test_ips_from_sources():
    sources = [
        "rtsp://192.168.0.50:554/Streaming/Channels/101",
        "rtsp://admin:pass@192.168.0.51/live",
        0,                       # int-камера игнорируется
        "rtsp://10.0.0.7:8554/cam",
        "/dev/video0",           # без IP
    ]
    assert ips_from_sources(sources) == {"192.168.0.50", "192.168.0.51", "10.0.0.7"}


def test_normalize_subnets():
    vals = ["192.168.0", "192.168.1.42", "10.0.0.0/24", "  ", "junk", "172.16.5.0/16"]
    assert normalize_subnets(vals) == {"192.168.0", "192.168.1", "10.0.0", "172.16.5"}


def test_normalize_subnets_empty():
    assert normalize_subnets([]) == set()
    assert normalize_subnets(["", "  "]) == set()


def test_hosts_for_prefixes():
    hosts = hosts_for_prefixes({"192.168.0", "10.0.0"})
    assert len(hosts) == 254 * 2
    assert "192.168.0.1" in hosts and "192.168.0.254" in hosts
    assert "10.0.0.128" in hosts
    assert "192.168.0.0" not in hosts and "192.168.0.255" not in hosts
