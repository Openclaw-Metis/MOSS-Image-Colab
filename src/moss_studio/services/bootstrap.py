"""Candidate Colab preparation; publishing requires the separate acceptance gates."""

import json
import subprocess
import sys
import venv
from pathlib import Path

from moss_studio.adapters.comfy import ComfyClient
from moss_studio.domain.contracts import ConflictError, ValidationError
from moss_studio.services.downloads import download_locked
from moss_studio.services.processes import ManagedProcess
from moss_studio.services.resources import inspect_runtime, l4_preflight
from moss_studio.storage.atomic import atomic_json, file_lock, private_dir


class ColabBootstrap:
    def __init__(
        self,
        repository: Path,
        root: Path = Path("/content/moss-stage1"),
        model_root: Path = Path("/content/models"),
    ):
        self.repository = Path(repository).resolve()
        self.root = private_dir(root)
        self.model_root = private_dir(model_root)
        self.runtime = json.loads((self.repository / "configs/runtime.lock.json").read_text())
        self.models = json.loads((self.repository / "configs/models.lock.json").read_text())
        self.comfy = self.root / "ComfyUI"
        self.python = self.root / "venv/bin/python"
        self.engine = ManagedProcess(self.root / ".runtime", "comfy")

    def prepare(self, *, allow_candidate: bool = False) -> None:
        if self.runtime["status"] != "released" and not allow_candidate:
            raise ValidationError("這是未放行的 Stage 1 探測環境，須明確允許 candidate")
        report = inspect_runtime(self.root)
        atomic_json(self.root / "environment.json", report)
        errors = l4_preflight(report)
        if errors:
            raise ValidationError("；".join(errors))
        with file_lock(self.root / ".prepare.lock"):
            pin = self.runtime["comfyui"]["commit"]
            if not self.comfy.exists():
                subprocess.run(
                    [
                        "git",
                        "clone",
                        self.runtime["comfyui"]["repo"],
                        str(self.comfy),
                    ],
                    check=True,
                )
            if self.comfy.is_symlink():
                raise ValidationError("引擎目錄不可為符號連結")
            dirty = subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=no"], cwd=self.comfy, text=True
            ).strip()
            if dirty:
                raise ConflictError("引擎有本地修改，保留現況，不自動覆寫")
            subprocess.run(["git", "checkout", "--detach", pin], cwd=self.comfy, check=True)
            # Colab's ensurepip is unavailable in some runtimes. Reuse its installed pip/torch.
            venv.EnvBuilder(with_pip=False, system_site_packages=True).create(self.root / "venv")
            subprocess.run([str(self.python), "-m", "pip", "--version"], check=True)
            lock = self.runtime.get("transitive_lock")
            requirements = self.repository / lock if lock else self.comfy / "requirements.txt"
            command = [
                str(self.python),
                "-m",
                "pip",
                "install",
                "-r",
                str(requirements),
                f"gradio=={self.runtime['gradio']}",
                f"huggingface-hub=={self.runtime['huggingface_hub']}",
            ]
            subprocess.run(command, check=True)
            with (self.root / "resolved-environment.txt").open("w") as stream:
                subprocess.run([str(self.python), "-m", "pip", "freeze"], stdout=stream, check=True)
            (self.comfy / "extra_model_paths.yaml").write_text(
                "moss_studio:\n  base_path: "
                + json.dumps(str(self.model_root))
                + "\n  diffusion_models: diffusion_models\n  text_encoders: text_encoders"
                + "\n  vae: vae\n  loras: loras\n  geometry_estimation: geometry_estimation\n"
            )

    def download(self, identifiers: list[str]) -> list[str]:
        indexed = {artifact["id"]: artifact for artifact in self.models["artifacts"]}
        if set(identifiers) - indexed.keys():
            raise ValidationError("模型清單中沒有此識別碼")
        artifacts = [indexed[identifier] for identifier in dict.fromkeys(identifiers)]
        remaining = sum(
            artifact["size_bytes"]
            for artifact in artifacts
            if not (self.model_root / artifact["filename"]).exists()
        )
        errors = l4_preflight(inspect_runtime(self.model_root), remaining)
        if errors:
            raise ValidationError("；".join(errors))
        return [str(download_locked(artifact, self.model_root)) for artifact in artifacts]

    def start_engine(self) -> dict:
        if not self.python.is_file():
            raise ValidationError("請先完成 prepare 與模型校驗")
        if not (self.comfy / "extra_model_paths.yaml").is_file():
            raise ValidationError("缺少本工具的模型路徑設定")
        current = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.comfy, text=True
        ).strip()
        if current != self.runtime["comfyui"]["commit"]:
            raise ValidationError("引擎版本與固定清單不同")
        command = [
            str(self.python),
            "main.py",
            "--listen",
            "127.0.0.1",
            "--port",
            "8188",
            "--disable-auto-launch",
            "--lowvram",
        ]
        return self.engine.start(command, self.comfy, 8188, ComfyClient().health, timeout=60)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Stage 1 Colab 探測環境（未放行）")
    parser.add_argument("action", choices=["prepare", "download", "start", "stop"])
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("/content/moss-stage1"))
    parser.add_argument("--model-root", type=Path, default=Path("/content/models"))
    parser.add_argument("--allow-candidate", action="store_true")
    parser.add_argument("--models", nargs="+", default=["sft_bf16", "qwen_int8", "vae_small"])
    args = parser.parse_args()
    bootstrap = ColabBootstrap(args.repository, args.root, args.model_root)
    if args.action == "prepare":
        bootstrap.prepare(allow_candidate=args.allow_candidate)
    elif args.action == "download":
        print(json.dumps(bootstrap.download(args.models)))
    elif args.action == "start":
        print(json.dumps(bootstrap.start_engine()))
    else:
        bootstrap.engine.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
