"""The Windows Firewall and install scripts: their dry runs say exactly what they would do, and refuse unsafe input."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts" / "lan"
POWERSHELL = shutil.which("powershell")
pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is not available")


def run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPTS / script), *args],
                          capture_output=True, text=True, timeout=120)


def test_firewall_dry_run_opens_two_ports_on_private_networks_for_the_listed_subnets_only():
    done = run("firewall-main-pc.ps1", "-Address", "192.168.1.10", "-Subnets", "192.168.1.0/24", "-DryRun")
    assert done.returncode == 0, done.stderr
    out = done.stdout
    assert "Profile=Private" in out and "Direction=Inbound" in out and "Protocol=TCP" in out
    assert "LocalPort=8443,8444" in out and "RemoteAddress=192.168.1.0/24" in out and "LocalAddress=192.168.1.10" in out
    assert "Any" not in out and "0.0.0.0" not in out and "Public" not in out


@pytest.mark.parametrize("subnet", ["8.8.8.0/24", "0.0.0.0/0", "192.168.0.0/8", "10.0.0.0/8"])
def test_firewall_script_refuses_public_or_too_wide_networks(subnet):
    done = run("firewall-main-pc.ps1", "-Address", "192.168.1.10", "-Subnets", subnet, "-DryRun")
    assert done.returncode != 0 and "New-NetFirewallRule" not in done.stdout


def test_firewall_script_refuses_every_network_card_address():
    done = run("firewall-main-pc.ps1", "-Address", "0.0.0.0", "-Subnets", "192.168.1.0/24", "-DryRun")
    assert done.returncode != 0


def test_install_dry_run_lists_every_step_and_changes_nothing():
    done = run("install-main-pc.ps1", "-Exe", r"C:\nowhere\pperp_api.exe", "-Address", "192.168.1.10", "-Subnets", "192.168.1.0/24", "-DryRun")
    assert done.returncode == 0, done.stderr
    out = done.stdout
    for step in ("lan init", "New-NetFirewallRule", "Register scheduled task 'PetrolPumpERP-MainPC'", "as SYSTEM", "lan run"):
        assert step in out, step
    assert out.count("[dry run]") >= 5
