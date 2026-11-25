# Name: Yu-Chien Chiu
# Student ID: 56176405
# Name: Mars Huang
# Student ID: 79666292
"""Per-run dependency isolation and host-only image build tests (no Docker needed)."""

import errno
import subprocess
from pathlib import Path

import pytest

import sandbox_runner
from project_dependencies import (
    DependencyNotApproved,
    image_for_dependencies,
    resolve_dependencies,
)

# File systems that refuse to create symlinks (e.g. some mounted/FAT volumes).
SYMLINK_UNSUPPORTED_ERRNOS = {errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP}


def test_project_specific_images_are_deterministic(tmp_path):
    quick = tmp_path / "quick"
    budget = tmp_path / "budget"
    quick.mkdir()
    budget.mkdir()
    (quick / "requirements.txt").write_text("streamlit\npytest\n")
    (budget / "requirements.txt").write_text("streamlit\npandas\nmatplotlib\npytest\n")
    a, b = resolve_dependencies(quick), resolve_dependencies(budget)
    assert a == ()
    assert b == ("matplotlib==3.10.7", "pandas==2.3.3")
    assert image_for_dependencies(a) != image_for_dependencies(b)
    assert image_for_dependencies(b) == image_for_dependencies(resolve_dependencies(budget))


@pytest.mark.parametrize("spec", [
    "-e .", "https://bad.example/thing.whl", "git+https://example.org/x",
    "requests", "-r other.txt", "matplotlib>=1", "matplotlib; python_version>'3'",
])
def test_unapproved_dependencies_fail_closed(tmp_path, spec):
    (tmp_path / "requirements.txt").write_text(spec + "\n")
    with pytest.raises(DependencyNotApproved):
        resolve_dependencies(tmp_path)


def test_build_approved_image_once_and_use_in_docker_run(monkeypatch, tmp_path):
    (tmp_path / "requirements.txt").write_text("matplotlib\n")
    commands = []
    monkeypatch.delenv("AI_CODER_BROKER_DIR", raising=False)
    monkeypatch.delenv("AI_CODER_RUNNER", raising=False)
    monkeypatch.setattr(sandbox_runner, "_BUILT_IMAGES", set())

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        if cmd[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(cmd, 1, "", "not found")
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    sandbox_runner.run_generated_python(tmp_path, ["-m", "pytest"])
    sandbox_runner.run_generated_python(tmp_path, ["-m", "pytest"])
    builds = [c for c in commands if c[:2] == ["docker", "build"]]
    runs = [c for c in commands if c[:2] == ["docker", "run"]]
    assert len(builds) == 1
    assert len(runs) == 2
    assert "EXTRA_PACKAGES=matplotlib==3.10.7" in builds[0]
    expected = image_for_dependencies(("matplotlib==3.10.7",))
    assert all(expected in c for c in runs)
    assert all("--network=none" in c and "--read-only" in c for c in runs)


def test_bad_dependency_never_starts_container(monkeypatch, tmp_path):
    (tmp_path / "requirements.txt").write_text("evil-private-package\n")
    monkeypatch.delenv("AI_CODER_BROKER_DIR", raising=False)
    monkeypatch.delenv("AI_CODER_RUNNER", raising=False)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("Docker must not run"))
    with pytest.raises(sandbox_runner.SandboxUnavailable, match="rejected"):
        sandbox_runner.run_generated_python(tmp_path, ["-m", "pytest"])


def test_symlinked_manifest_rejected(tmp_path):
    """Uses a real OS symlink; skipped only where this account cannot create one."""
    outside = tmp_path / "outside.txt"
    outside.write_text("matplotlib\n")
    project = tmp_path / "project"
    project.mkdir()
    try:
        (project / "requirements.txt").symlink_to(outside)
    except NotImplementedError as exc:
        pytest.skip(f"Symlinks are not implemented on this platform: {exc}")
    except OSError as exc:
        # Skip ONLY "not allowed / not supported" errors; anything else is a real failure.
        # WinError 1314 = ERROR_PRIVILEGE_NOT_HELD (Windows without Developer Mode/admin).
        if getattr(exc, "winerror", None) == 1314 or exc.errno in SYMLINK_UNSUPPORTED_ERRNOS:
            pytest.skip(f"Cannot create symlinks in this environment: {exc}")
        raise
    # The rejection logic is also covered on every platform by the test below.
    with pytest.raises(DependencyNotApproved, match="Symlinked"):
        resolve_dependencies(project)


def test_symlink_rejection_does_not_need_os_symlink_support(tmp_path, monkeypatch):
    """Runs on every platform: a manifest reported as a symlink is never read."""
    (tmp_path / "requirements.txt").write_text("matplotlib\n")
    real_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink",
        lambda self: self.name == "requirements.txt" or real_is_symlink(self),
    )
    monkeypatch.setattr(Path, "read_text",
                        lambda *a, **kw: pytest.fail("Symlinked manifest must not be read"))
    with pytest.raises(DependencyNotApproved, match="Symlinked"):
        resolve_dependencies(tmp_path)


def test_oversized_manifest_rejected(tmp_path):
    (tmp_path / "requirements.txt").write_bytes(b"#" * 4097)
    with pytest.raises(DependencyNotApproved, match="4 KiB"):
        resolve_dependencies(tmp_path)


def test_manifest_at_size_limit_is_accepted(tmp_path):
    # write_bytes avoids Windows newline translation changing the file size.
    (tmp_path / "requirements.txt").write_bytes(b"#" * 4096)
    assert resolve_dependencies(tmp_path) == ()


def test_explicit_unapproved_version_rejected(tmp_path):
    (tmp_path / "requirements.txt").write_text("matplotlib==0.1\n")
    with pytest.raises(DependencyNotApproved, match="Unapproved version"):
        resolve_dependencies(tmp_path)
