from pathlib import Path


def test_production_dependencies_are_exactly_pinned():
    lines = [
        line.strip()
        for line in Path("requirements.txt").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert lines == [
        "requests==2.34.2",
        "Flask==3.1.3",
        "gunicorn==23.0.0",
    ]
    assert all("==" in line for line in lines)


def test_python_runtime_is_exactly_pinned_to_tested_version():
    assert Path(".python-version").read_text(
        encoding="utf-8"
    ).strip() == "3.14.3"
