from backend import main


def test_save_restore_and_reset_are_undoable(client):
    original = main.DATA_FILE.read_bytes()
    demo = client.get("/api/scene").json()
    assert client.get("/api/storage").json() == {"saved_exists": False}
    assert client.post("/api/restore").status_code == 404
    assert client.get("/api/scene").json() == demo
    assert main.UNDO == []
    client.post("/api/autofix")
    fixed = client.get("/api/scene").json()
    assert client.post("/api/save").json() == {"saved": True}
    saved = main.SAVED_FILE.read_bytes()
    assert main.DATA_FILE.read_bytes() == original
    assert main.load_scene().model_dump(by_alias=True) == fixed
    assert client.get("/api/storage").json() == {"saved_exists": True}

    assert client.post("/api/reset").json()["summary"]["violations"] == 9
    assert main.SAVED_FILE.read_bytes() == saved
    assert client.post("/api/undo").json()["summary"]["score"] == 100
    assert client.post("/api/redo").json()["summary"]["violations"] == 9

    assert client.post("/api/restore").json()["summary"]["score"] == 100
    assert client.post("/api/undo").json()["summary"]["violations"] == 9
    assert client.post("/api/redo").json()["summary"]["score"] == 100
    assert main.DATA_FILE.read_bytes() == original
    assert main.SAVED_FILE.read_bytes() == saved


def test_corrupt_saved_layout_does_not_mutate_state(client):
    before = client.get("/api/scene").json()
    main.SAVED_FILE.write_text("{", encoding="utf-8")
    response = client.post("/api/restore?lang=en")
    assert response.status_code == 500
    assert "Cannot load layout" in response.json()["detail"]
    assert client.get("/api/scene").json() == before
    assert main.UNDO == []


def test_save_failure_preserves_existing_save(client, monkeypatch):
    client.post("/api/save")
    original = main.SAVED_FILE.read_bytes()

    def fail_replace(self, target):
        raise PermissionError("test: file is locked")

    monkeypatch.setattr(type(main.SAVED_FILE), "replace", fail_replace)
    response = client.post("/api/save?lang=en")
    assert response.status_code == 500
    assert "Save failed" in response.json()["detail"]
    assert main.SAVED_FILE.read_bytes() == original
    assert list(main.SAVED_FILE.parent.glob(".layout-*.tmp")) == []
