"""Тесты чистых помощников автообнаружения камер (без сети)."""
from backend.discovery import (
    ips_from_ws_responses, candidate_urls, subnet_hosts, name_for_ip,
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
