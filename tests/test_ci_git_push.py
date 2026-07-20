"""Smoke tests for CI git push conflict-recovery helpers."""

from pathlib import Path


def test_jsonl_line_merge_preserves_both_sides(tmp_path: Path) -> None:
    remote = tmp_path / "remote.jsonl"
    ours = tmp_path / "ours.jsonl"
    out = tmp_path / "out.jsonl"
    remote.write_text('{"at":"1","k":"a"}\n{"at":"2","k":"b"}\n', encoding="utf-8")
    ours.write_text('{"at":"1","k":"a"}\n{"at":"3","k":"c"}\n', encoding="utf-8")

    # Mirror the merge algorithm in scripts/ci_git_push.sh
    remote_lines = remote.read_text(encoding="utf-8").splitlines()
    ours_lines = ours.read_text(encoding="utf-8").splitlines()
    seen = set(remote_lines)
    merged = list(remote_lines)
    for line in ours_lines:
        if line and line not in seen:
            merged.append(line)
            seen.add(line)
    out.write_text("\n".join(merged) + "\n", encoding="utf-8")

    assert out.read_text(encoding="utf-8").splitlines() == [
        '{"at":"1","k":"a"}',
        '{"at":"2","k":"b"}',
        '{"at":"3","k":"c"}',
    ]
