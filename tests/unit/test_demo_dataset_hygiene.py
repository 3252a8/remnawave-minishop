from pathlib import Path


def test_demo_dataset_is_marked_generated_and_documented() -> None:
    dataset_path = Path("frontend/src/lib/webapp/demoDataset.js")
    readme_path = Path("frontend/src/lib/webapp/demoDataset.README.md")

    header = dataset_path.read_text(encoding="utf-8").splitlines()[:3]

    assert header == [
        "// GENERATED - do not edit by hand.",
        "// Source: anonymized demo snapshot described in `generatedFrom` below.",
        "// Regeneration policy: see `demoDataset.README.md` in this directory.",
    ]
    assert readme_path.exists()
