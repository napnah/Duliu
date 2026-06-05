from duliu_mcp.services.polygon_exporter import PolygonExporter, TestDataExporter


def test_export_samples(tmp_path):
    problem = {
        "id": "00000000-0000-0000-0000-000000000001",
        "title": "Demo",
        "spec_json": {
            "limits": {"time_ms": 2000, "memory_mb": 512},
            "samples": [{"input": "1 2", "output": "3"}],
        },
    }
    exporter = TestDataExporter(export_root=tmp_path)
    result = exporter.export(problem, samples_only=True)

    assert result["status"] == "ok"
    assert result["test_count"] == 1
    assert (tmp_path / problem["id"] / "tests" / "1.in").exists()
    assert (tmp_path / problem["id"] / "tests" / "1.out").exists()


def test_polygon_package_scaffold(tmp_path):
    problem = {
        "id": "00000000-0000-0000-0000-000000000002",
        "title": "A+B",
        "spec_json": {
            "limits": {"time_ms": 1000, "memory_mb": 256},
            "samples": [{"input": "1 1", "output": "2"}],
        },
    }
    artifacts = [
        {"kind": "statement", "content_text": "<p>A+B</p>", "language": None},
        {"kind": "std", "content_text": "int main(){}", "language": "cpp"},
    ]
    exporter = PolygonExporter(export_root=tmp_path)
    result = exporter.export(problem, artifacts, language="chinese")

    root = tmp_path / problem["id"] / "polygon_package"
    assert result["status"] == "ok"
    assert (root / "problem.xml").exists()
    assert (root / "statements" / "chinese.html").exists()
    assert (root / "solutions" / "standard.cpp").exists()
    assert (root / "tests" / "1.in").exists()
