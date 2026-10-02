import re
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _app_version():
    version_text = (ROOT / "source" / "version.py").read_text()
    match = re.search(r'__version__\s*=\s*"([^"]+)"', version_text)
    assert match, "source/version.py must define __version__"
    return match.group(1)


def test_version_metadata_is_consistent_everywhere():
    version = _app_version()

    readme = (ROOT / "README.md").read_text()
    assert f"`v{version}`" in readme
    assert f"WxCleaner-{version}.app" in readme

    spec = (ROOT / "packaging" / "WxCleaner.spec").read_text()
    assert f'APP_VERSION = "{version}"' in spec
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
