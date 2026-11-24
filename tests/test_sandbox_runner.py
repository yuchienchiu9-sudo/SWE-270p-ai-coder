# Name: Yu-Chien Chiu
# Student ID: 56176405
# Name: Mars Huang
# Student ID: 79666292
"""Runner configuration tests; no Docker or Gemini required."""

import subprocess
import sys

import pytest

import sandbox_runner as sandbox


def test_docker_default_and_resource_limits(monkeypatch, tmp_path):
    monkeypatch.delenv(sandbox.RUNNER_ENV, raising=False)
    observed = {}

    def fake_run(cmd, **kwargs):
        observed.update(cmd=cmd, kwargs=kwargs)
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = sandbox.run_generated_python(tmp_path, ["-m", "pytest", "test_app.py"])
    cmd = observed["cmd"]
    assert result.stdout == "ok"
    for flag in ("--network=none", "--read-only", "--cap-drop=ALL", "--pids-limit=64", "--memory=512m", "--cpus=1", "--security-opt=no-new-privileges:true"):
        assert flag in cmd
    assert "--user=65534:65534" in cmd
    assert f"type=bind,source={tmp_path.resolve()},target=/workspace,readonly" in cmd
    assert "pytest" in cmd
    assert "--env=GEMINI_API_KEY" not in cmd
    assert observed["kwargs"]["timeout"] == 60


def test_no_docker_fails_closed(monkeypatch, tmp_path):
    monkeypatch.delenv(sandbox.RUNNER_ENV, raising=False)

    def missing(*args, **kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(sandbox.SandboxUnavailable, match="Docker CLI not found"):
        sandbox.run_generated_python(tmp_path, ["-m", "pytest"])


def test_docker_launch_error_fails_closed(monkeypatch, tmp_path):
    monkeypatch.delenv(sandbox.RUNNER_ENV, raising=False)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 125, "", "image not found"))
    with pytest.raises(sandbox.SandboxUnavailable, match="could not start"):
        sandbox.run_generated_python(tmp_path, ["-m", "pytest"])


def test_bad_mode_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv(sandbox.RUNNER_ENV, "unknown")
    with pytest.raises(sandbox.SandboxUnavailable, match="Invalid"):
        sandbox.run_generated_python(tmp_path, ["-m", "pytest"])


def test_host_mode_is_explicit_and_strips_secret_env(monkeypatch, tmp_path):
    monkeypatch.setenv(sandbox.RUNNER_ENV, "host")
    monkeypatch.setenv("GEMINI_API_KEY", "sensitive")
    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(cmd=cmd, env=kwargs["env"])
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    sandbox.run_generated_python(tmp_path, ["-V"])
    assert captured["cmd"] == [sys.executable, "-V"]
    assert "GEMINI_API_KEY" not in captured["env"]


def test_normal_test_failure_is_not_sandbox_failure(monkeypatch, tmp_path):
    monkeypatch.delenv(sandbox.RUNNER_ENV, raising=False)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "FAILED", ""))
    result = sandbox.run_generated_python(tmp_path, ["-m", "pytest"])
    assert result.returncode == 1


def test_timeout_triggers_container_cleanup(monkeypatch, tmp_path):
    monkeypatch.delenv(sandbox.RUNNER_ENV, raising=False)
    commands = []

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        if cmd[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(subprocess.TimeoutExpired):
        sandbox.run_generated_python(tmp_path, ["-m", "pytest"])
    assert commands[1][:3] == ["docker", "rm", "-f"]
    assert commands[1][3] == commands[0][commands[0].index("--name") + 1]
