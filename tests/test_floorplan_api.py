"""Тесты эндпоинтов плана здания (POST/GET/DELETE /api/floorplan).

Флоу калибровки строится на этой подложке, поэтому проверяем загрузку, отдачу,
валидацию расширения и удаление. Каталог плана патчим в tmp, чтобы не трогать
реальный data/.
"""
import io
import numpy as np
import pytest
from flask import Flask


@pytest.fixture
def client(monkeypatch, tmp_path, state):
    import backend.api.detection as det
    monkeypatch.setattr(det, "_FLOORPLAN_DIR", tmp_path / "floorplan")
    app = Flask(__name__)
    det.configure_detection_routes(
        app, state, annotated_buffers={},
        generate_live_feed=lambda *_a, **_k: iter(()),
        start_live=lambda: None, stop_live=lambda: None, model=None)
    app.config["TESTING"] = True
    return app.test_client()


def _png_bytes():
    import cv2
    img = np.zeros((8, 8, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


class TestFloorplanApi:
    def test_get_none_is_404(self, client):
        assert client.get("/api/floorplan").status_code == 404

    def test_upload_then_get(self, client):
        data = {"file": (io.BytesIO(_png_bytes()), "plan.png")}
        r = client.post("/api/floorplan", data=data, content_type="multipart/form-data")
        assert r.status_code == 200 and r.get_json()["status"] == "uploaded"
        g = client.get("/api/floorplan")
        assert g.status_code == 200
        assert g.data == _png_bytes()

    def test_upload_rejects_bad_extension(self, client):
        data = {"file": (io.BytesIO(b"not an image"), "plan.txt")}
        r = client.post("/api/floorplan", data=data, content_type="multipart/form-data")
        assert r.status_code == 400

    def test_upload_requires_file(self, client):
        r = client.post("/api/floorplan", data={}, content_type="multipart/form-data")
        assert r.status_code == 400

    def test_upload_replaces_previous(self, client):
        client.post("/api/floorplan",
                    data={"file": (io.BytesIO(_png_bytes()), "plan.png")},
                    content_type="multipart/form-data")
        # Загружаем второй раз как .jpg — старый .png должен исчезнуть (один файл).
        import cv2
        ok, buf = cv2.imencode(".jpg", np.zeros((8, 8, 3), dtype=np.uint8))
        client.post("/api/floorplan",
                    data={"file": (io.BytesIO(buf.tobytes()), "plan.jpg")},
                    content_type="multipart/form-data")
        import backend.api.detection as det
        import glob
        files = glob.glob(str(det._FLOORPLAN_DIR / "plan.*"))
        assert len(files) == 1 and files[0].endswith(".jpg")

    def test_delete(self, client):
        client.post("/api/floorplan",
                    data={"file": (io.BytesIO(_png_bytes()), "plan.png")},
                    content_type="multipart/form-data")
        assert client.delete("/api/floorplan").status_code == 200
        assert client.get("/api/floorplan").status_code == 404
