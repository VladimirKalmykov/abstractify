from __future__ import annotations

from pathlib import Path

from abstractify.config import EMBED_MODES, Config, save_config
from abstractify.embeddings import build_embedder
from abstractify.embeddings.local import download_model
from abstractify.paths import config_path, project_dir
from abstractify.store import Store

SKILL_MARKER_BEGIN = "<!-- abstractify:begin -->"
SKILL_MARKER_END = "<!-- abstractify:end -->"


def init_project(
    root: Path,
    *,
    embed_mode: str = "none",
    embed_url: str = "",
    embed_model: str | None = None,
    custom_adapter: str = "",
    force: bool = False,
    example: bool = False,
    download_model_now: bool = False,
) -> Config:
    root = root.resolve()
    if embed_mode not in EMBED_MODES:
        raise ValueError(f"embed_mode must be one of {EMBED_MODES}")
    if config_path(root).exists() and not force:
        raise FileExistsError(
            f"Abstractify already initialized at {project_dir(root)}. Use --force to reconfigure."
        )
    cfg = Config(
        embed_mode=embed_mode,
        embed_url=embed_url,
        custom_adapter=custom_adapter,
    )
    if embed_model:
        cfg.embed_model = embed_model
    project_dir(root).mkdir(parents=True, exist_ok=True)
    save_config(root, cfg)
    store = Store(root, cfg, build_embedder(cfg, root))
    if example:
        store.seed_example()
    store.close()
    install_skill(root)
    if download_model_now:
        if embed_mode != "local":
            raise ValueError("--download-model only applies to --embed-mode local")
        download_model(cfg.embed_model)
    return cfg


def install_skill(root: Path) -> None:
    from importlib import resources

    skill_src = resources.files("abstractify").joinpath("skills/SKILL.md").read_text(encoding="utf-8")
    dest = root / ".cursor" / "skills" / "abstractify" / "SKILL.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(skill_src, encoding="utf-8")
    always = resources.files("abstractify").joinpath("skills/always-on.md").read_text(encoding="utf-8")
    agents = root / "AGENTS.md"
    block = f"{SKILL_MARKER_BEGIN}\n{always.rstrip()}\n{SKILL_MARKER_END}\n"
    if agents.exists():
        text = agents.read_text(encoding="utf-8")
        if SKILL_MARKER_BEGIN in text and SKILL_MARKER_END in text:
            pre = text.split(SKILL_MARKER_BEGIN, 1)[0]
            post = text.split(SKILL_MARKER_END, 1)[1]
            agents.write_text(pre + block + post.lstrip("\n"), encoding="utf-8")
        else:
            agents.write_text(text.rstrip() + "\n\n" + block, encoding="utf-8")
    else:
        agents.write_text(block, encoding="utf-8")
