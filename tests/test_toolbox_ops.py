"""Reset / restore clear every uploads subfolder the app writes to."""

from app import toolbox_ops


def test_clear_uploads_empties_screenshots_exports_and_knowledge(tmp_path, monkeypatch):
    monkeypatch.setattr(toolbox_ops, "UPLOADS_DIR", str(tmp_path))
    for sub in ("screenshots", "exports", "knowledge"):
        (tmp_path / sub / "7").mkdir(parents=True)
        (tmp_path / sub / "7" / "f.png").write_bytes(b"x")
        (tmp_path / sub / ".gitkeep").write_text("")
    toolbox_ops._clear_uploads()
    for sub in ("screenshots", "exports", "knowledge"):
        assert [p.name for p in (tmp_path / sub).iterdir()] == [".gitkeep"]
