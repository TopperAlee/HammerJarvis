from pathlib import Path


def test_manual_launcher_scripts_exist() -> None:
    assert Path("scripts/disable-desktop-agent-autostart.ps1").is_file()
    assert Path("scripts/start-hammer-jarvis.ps1").is_file()
    assert Path("scripts/create-desktop-shortcut.ps1").is_file()
    assert Path("scripts/stop-hammer-jarvis.ps1").is_file()


def test_disable_autostart_script_handles_missing_task_safely() -> None:
    content = Path("scripts/disable-desktop-agent-autostart.ps1").read_text(encoding="utf-8")

    assert '$taskName = "Hammer Jarvis Desktop Agent"' in content
    assert "Get-ScheduledTask" in content
    assert "Disable-ScheduledTask" in content
    assert "SilentlyContinue" in content
    assert "nicht vorhanden" in content


def test_manual_launcher_uses_venv_health_check_and_dashboard_url() -> None:
    content = Path("scripts/start-hammer-jarvis.ps1").read_text(encoding="utf-8")

    assert ".venv\\Scripts\\python.exe" in content
    assert "http://127.0.0.1:8001/assistant/health" in content
    assert "http://127.0.0.1:8001/dashboard" in content
    assert "uvicorn" in content
    assert "app.main:app" in content
    assert "--host" in content
    assert "127.0.0.1" in content
    assert "--port" in content
    assert "8001" in content
    assert "Start-Process" in content
    assert "WindowStyle Hidden" in content


def test_desktop_shortcut_targets_manual_launcher_without_admin() -> None:
    content = Path("scripts/create-desktop-shortcut.ps1").read_text(encoding="utf-8")

    assert "Hammer Jarvis.lnk" in content
    assert "powershell.exe" in content
    assert "-ExecutionPolicy Bypass" in content
    assert "start-hammer-jarvis.ps1" in content
    assert "WorkingDirectory" in content
    assert "RunAs" not in content


def test_stop_hammer_jarvis_only_targets_local_port_8001() -> None:
    content = Path("scripts/stop-hammer-jarvis.ps1").read_text(encoding="utf-8")

    assert "Get-NetTCPConnection" in content
    assert "-LocalPort 8001" in content
    assert 'LocalAddress -eq "127.0.0.1"' in content
    assert "Stop-Process" in content
    assert "8001" in content


def test_readme_documents_manual_desktop_launcher() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "start-hammer-jarvis.ps1" in content
    assert "create-desktop-shortcut.ps1" in content
    assert "disable-desktop-agent-autostart.ps1" in content
    assert "stop-hammer-jarvis.ps1" in content
    assert "Desktop-Verknüpfung" in content
