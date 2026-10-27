from __future__ import annotations

import json
from pathlib import Path

from abstractify.config import EMBED_MODES, Config, allocate_localhost_ports, load_config, save_config
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
    only_agents: bool = False,
    only_skill: bool = False,
    only_mcp: bool = False,
) -> Config:
    root = root.resolve()
    if sum((only_skill, only_agents, only_mcp)) > 1:
        raise ValueError("Pass only one of --only-skill, --only-agents, or --only-mcp.")
    if only_mcp:
        if not config_path(root).is_file():
            raise FileNotFoundError(
                f"Abstractify is not initialized at {root}. "
                "There is no project to configure MCP for. Run `abstractify init` first."
            )
        install_cursor_mcp(root)
        return load_config(root)
    if only_skill:
        if not config_path(root).is_file():
            raise FileNotFoundError(
                f"Abstractify is not initialized at {root}. "
                "There is no project to install skills into. Run `abstractify init` first."
            )
        install_skill_files(root)
        return load_config(root)
    if only_agents:
        if not config_path(root).is_file():
            raise FileNotFoundError(
                f"Abstractify is not initialized at {root}. "
                "There is no agent instruction to update. Run `abstractify init` first."
            )
        cfg = load_config(root)
        install_agents_block(root, cfg)
        return cfg
    if embed_mode not in EMBED_MODES:
        raise ValueError(f"embed_mode must be one of {EMBED_MODES}")
    if config_path(root).exists() and not force:
        raise FileExistsError(
            f"Abstractify already initialized at {project_dir(root)}. Use --force to reconfigure."
        )
    host = "127.0.0.1"
    mcp_port, ui_port = allocate_localhost_ports(host)
    project_dir(root).mkdir(parents=True, exist_ok=True)
    cfg = Config(
        embed_mode=embed_mode,
        embed_url=embed_url,
        custom_adapter=custom_adapter,
        ui_host=host,
        mcp_port=mcp_port,
        ui_port=ui_port,
    )
    if embed_model:
        cfg.embed_model = embed_model
    save_config(root, cfg)
    store = Store(root, cfg, build_embedder(cfg, root))
    if example:
        store.seed_example()
    store.close()
    install_skill(root, cfg)
    install_cursor_mcp(root)
    if download_model_now:
        if embed_mode != "local":
            raise ValueError("--download-model only applies to --embed-mode local")
        download_model(root, cfg)
    return cfg


def _ports_skill_lines(cfg: Config) -> str:
    host = cfg.ui_host or "127.0.0.1"
    return (
        f"- This project's MCP HTTP is at `{host}:{cfg.mcp_port}` (endpoint `/mcp`).\n"
        f"- This project's UI is at `http://{host}:{cfg.ui_port}`.\n"
    )


def install_cursor_mcp(root: Path) -> Path:
    """Write or update the Abstractify stdio server in .cursor/mcp.json. Other entries stay."""
    dest = root / ".cursor" / "mcp.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if dest.is_file():
        raw = dest.read_text(encoding="utf-8").strip()
        if raw:
            try:
                loaded = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Cannot update {dest}: it is not valid JSON ({exc.msg}).") from exc
            if not isinstance(loaded, dict):
                raise ValueError(f"Cannot update {dest}: the top level must be a JSON object.")
            data = loaded
    servers = data.get("mcpServers", {})
    if servers is None:
        servers = {}
    if not isinstance(servers, dict):
        raise ValueError(f"Cannot update {dest}: mcpServers must be a JSON object.")
    servers["abstractify"] = {
        "command": "abstractify",
        "args": ["serve", root.resolve().as_posix()],
    }
    data["mcpServers"] = servers
    dest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest


def install_skill_files(root: Path) -> list[Path]:
    """Write the skills an initialized project needs. Does not touch config, the db, or AGENTS.md.

    Each skill written under .agents/skills is also written under .parser/skills when the
    project already has a parsers directory. That directory is never created.
    """
    from importlib import resources

    written: list[Path] = []
    agents_skills = root / ".agents" / "skills"
    copies = (
        ("skills/SKILL.md", root / ".cursor" / "skills" / "abstractify" / "SKILL.md"),
        ("skills/agents-skill.md", agents_skills / "abstractify" / "SKILL.md"),
    )
    mirror_parser = (root / "parsers").is_dir()
    for name, dest in copies:
        text = resources.files("abstractify").joinpath(name).read_text(encoding="utf-8")
        written.extend(_write_skill(dest, text))
        if mirror_parser and dest.is_relative_to(agents_skills):
            parser_dest = root / ".parser" / "skills" / dest.relative_to(agents_skills)
            written.extend(_write_skill(parser_dest, text))
    return written


def _write_skill(dest: Path, text: str) -> list[Path]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return [dest]


def install_skill(root: Path, cfg: Config) -> None:
    install_skill_files(root)
    install_agents_block(root, cfg)


def install_agents_block(root: Path, cfg: Config) -> None:
    from importlib import resources

    always = resources.files("abstractify").joinpath("skills/always-on.md").read_text(encoding="utf-8")
    agents = root / "AGENTS.md"
    body = always.rstrip() + "\n" + _ports_skill_lines(cfg)
    block = f"{SKILL_MARKER_BEGIN}\n{body}\n{SKILL_MARKER_END}\n"
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
