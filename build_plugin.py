"""Build a clean Sanka-compatible DDAS PLUS plugin ZIP."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


PLUGIN_FILES = (
    "plugin.json",
    "README.md",
    "requirements.txt",
    "main.py",
    "common/__init__.py",
    "common/browser.py",
    "common/config_generator.py",
    "common/config_schema.py",
    "common/data_editor.py",
    "common/file_dialogs.py",
    "common/logger.py",
    "common/log_policy.py",
    "common/settings.py",
    "common/task_runner.py",
    "common/task_models.py",
    "common/task_results.py",
    "common/result_exporter.py",
    "common/unified_settings.py",
    "deedraw/__init__.py",
    "deedraw/credentials.py",
    "deedraw/config_adapter.py",
    "deedraw/task.py",
    "deedraw/view.py",
    "pim/__init__.py",
    "pim/task.py",
    "pim/view.py",
    "icon.ico",
    "icon.icns",
)


def validate_project(project_dir: Path) -> dict:
    manifest_path = project_dir / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = [name for name in PLUGIN_FILES if not (project_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"插件缺少文件: {', '.join(missing)}")
    if manifest.get("runtime") != ["python"]:
        raise ValueError("DDAS PLUS 插件必须声明 Python 运行时")
    if manifest.get("entry") not in PLUGIN_FILES:
        raise ValueError("plugin.json 的入口文件未包含在插件白名单中")
    return manifest


def build_plugin(project_dir: Path, output_path: Path) -> Path:
    manifest = validate_project(project_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name in PLUGIN_FILES:
            archive.write(project_dir / name, arcname=name)
    print(f"已生成 {manifest['name']} {manifest['version']}: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="输出 ZIP 路径")
    args = parser.parse_args()
    project_dir = Path(__file__).resolve().parent
    manifest = validate_project(project_dir)
    default_name = f"{manifest['id']}-v{manifest['version']}.zip"
    build_plugin(project_dir, args.output or project_dir / "dist" / default_name)


if __name__ == "__main__":
    main()
