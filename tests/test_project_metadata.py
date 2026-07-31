from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_version_metadata_is_2_0_0_everywhere():
    version_file = ROOT / "source" / "version.py"
    assert version_file.exists()
    version_text = version_file.read_text()
    assert '__version__ = "2.0.0"' in version_text

    readme = (ROOT / "README.md").read_text()
    assert "`v2.0.0`" in readme
    assert "WxCleaner-2.0.0.app" in readme

    spec = (ROOT / "packaging" / "WxCleaner.spec").read_text()
    assert 'APP_VERSION = "2.0.0"' in spec
    assert "target_arch='arm64'" in spec
    assert "bundle_identifier='com.zzjjuut.WxCleaner'" in spec
    assert "'CFBundleShortVersionString': APP_VERSION" in spec
    assert "'CFBundleVersion': APP_VERSION" in spec


def test_release_build_automation_is_checked_in():
    build_script = ROOT / "scripts" / "build_release.sh"
    assert build_script.exists()
    script = build_script.read_text()
    assert "pytest tests -v" in script
    assert "codesign --verify --deep --strict" in script
    assert "WxCleaner-macOS-arm64-v${APP_VERSION}.zip" in script
    assert "PYTHON_BOOTSTRAP" in script
    assert "import tkinter" in script
    assert "COPYFILE_DISABLE=1 ditto -c -k --norsrc --keepParent" in script

    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    assert workflow.exists()
    workflow_text = workflow.read_text()
    assert "pytest tests -v" in workflow_text
    assert "pyinstaller" in workflow_text


def test_legacy_bundled_source_is_not_a_current_entrypoint():
    assert not (ROOT / "source" / "WxCleaner_bundled.py").exists()
    assert (ROOT / "legacy" / "WxCleaner_bundled.py").exists()
