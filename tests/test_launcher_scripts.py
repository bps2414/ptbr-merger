from pathlib import Path


def test_batch_launcher_delegates_to_hidden_powershell_script():
    content = Path("START_PTBRMERGER.bat").read_text(encoding="utf-8", errors="replace")

    assert "scripts\\start-ptbrmerger-hidden.ps1" in content
    assert "ExecutionPolicy Bypass" in content


def test_hidden_launcher_prefers_py_launcher_and_mentions_store_alias():
    content = Path("scripts/start-ptbrmerger-hidden.ps1").read_text(encoding="utf-8", errors="replace")

    assert 'Test-Command "py.exe"' in content
    assert '@("-3") + $pythonArgs' in content
    assert "Microsoft Store" in content
    assert "127.0.0.1" in content
    assert "8787" in content
