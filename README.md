# Abstractify

Agent-written **abstraction graphs** over a project: SQLite source of truth, MCP read/write, and a live localhost UI.

```bash
pip install -e '.[dev]'
abstractify init --embed-mode none --example
abstractify ui          # http://127.0.0.1:8765
abstractify serve       # MCP stdio
abstractify affected --git
```

- Concept: [docs/concept.md](docs/concept.md)
- Onboarding / architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Команды CLI

Точка входа: `abstractify` (`abstractify.cli:main`). У большинства команд необязательный путь к корню проекта — позиционный аргумент или `--path` (по умолчанию текущий каталог). `abstractify --version` печатает версию.

**`init`** — поставить Abstractify в проект.

```bash
abstractify init [PATH] [--embed-mode local|rest|none|custom] [--embed-url URL] [--embed-model NAME] [--custom-adapter FILE] [--force] [--example] [--download-model] [--only-agents]
```

`--embed-mode` по умолчанию `none`. `--example` кладёт маленький пример графа. `--download-model` качает локальную модель (только с `--embed-mode local`). `--only-agents` обновляет лишь блок в `AGENTS.md` и отказывается, если проект ещё не инициализирован. `--force` перенастраивает уже инициализированный проект.

```bash
abstractify init --embed-mode none --example
```

**`serve`** — MCP-сервер. `--transport` — `stdio` (по умолчанию) или `http`. `--host` по умолчанию `127.0.0.1`. `--port 0` берёт `mcp_port` из конфига.

```bash
abstractify serve --transport http
```

**`ui`** — локальный веб-интерфейс. `--port 0` берёт `ui_port` из конфига. `--open` открывает браузер. Хост должен быть loopback.

```bash
abstractify ui --open
```

**`start`** — MCP по HTTP и UI вместе. Сам останавливается после `--timeout` секунд без запросов (по умолчанию 3600). `--always-on` отключает этот простой.

```bash
abstractify start --timeout 600
```

**`status`** — проверяет, отвечают ли serve и UI на портах из конфига. Печатает `connected` или `disconnected`.

```bash
abstractify status
```

**`embeddings enable`** — включает эмбеддинги без повторного `init`. `--mode local|rest` обязателен. `--url` — адрес REST (если пусто, для `rest` подставляется сервис на порту 7342). `--no-backfill` только пишет конфиг, без дозаполнения векторов.

```bash
abstractify embeddings enable --mode local
```

**`embeddings backfill`** — считает векторы для сущностей, у которых их ещё нет. Режим в конфиге уже должен быть задан.

```bash
abstractify embeddings backfill
```

**`affected`** — сущности и графы, связанные с изменёнными файлами. Ничего сам не переписывает. Нужны пути файлов и/или `--git`.

```bash
abstractify affected --git
abstractify affected src/abstractify/cli.py
```

**`search`** — поиск сущностей (текст и семантика, если эмбеддинги включены). `-k` — сколько результатов (по умолчанию 20).

```bash
abstractify search "image generation" -k 10
```

**`path`** — как связаны две абстракции. По умолчанию путь ненаправленный; `--directed` ищет только по направлению рёбер. `--graph` ограничивает одним графом. Корень проекта задаётся флагом `--path`.

```bash
abstractify path "API Gateway" "Auth Service" --graph <id>
```

**`explain`** — одна абстракция и её окружение.

```bash
abstractify explain "Auth Service"
```

**`graph list`** — список графов. `--kind structural|flow` фильтрует тип.

```bash
abstractify graph list --kind flow
```

**`graph get`** — один граф по id.

```bash
abstractify graph get <id>
```

**`graph create`** — новый граф. Обязательны `--name`, `--kind structural|flow`, `--principle`. Дальше `--description`, `--from-json FILE`, `--confirm-large` (если граф больше обычного лимита).

```bash
abstractify graph create --name "Image flow" --kind flow --principle "Стадии запроса от UI до результата" --from-json graph.json
```

**`graph update`** — правит граф по id. Те же флаги, что у create, все необязательные; `--from-json` заменяет состав.

```bash
abstractify graph update <id> --description "Уточнённый срез"
```

**`graph delete`** — удаляет граф по id.

```bash
abstractify graph delete <id>
```

**`entity list`** — список сущностей. `--query` ищет по тексту, `--graph` оставляет один граф.

```bash
abstractify entity list --query gateway
```

**`entity upsert`** — создать или обновить сущность. `--name` обязателен. `--description`, `--graph`, `--id`. `--code-ref` можно повторять: `path[:start[:end]]`.

```bash
abstractify entity upsert --name "Auth Service" --graph <id> --code-ref src/auth/service.py:10:120
```

**`snapshot create`** — снимок графа. Необязательный `--label`.

```bash
abstractify snapshot create <id> --label "before refactor"
```

**`snapshot list`** — снимки. `--graph` ограничивает одним графом.

```bash
abstractify snapshot list --graph <id>
```

## Local embeddings on an existing project

You can turn on vector search **without re-running `abstractify init`**. Graphs and entities in `.abstractify/abstractify.db` stay as they are; there is no migration or separate index build.

1. Install the local extra (FastEmbed, not sentence-transformers):

   ```bash
   pip install 'abstractify[local]'
   ```

2. Edit `.abstractify/config.toml` in the project root:

   ```toml
   embed_mode = "local"
   # optional overrides (defaults shown):
   # embed_model = "intfloat/multilingual-e5-large"
   # embed_dimensions = 1024
   # embed_batch_size = 16
   ```

3. Restart anything that talks to the store (`abstractify serve`, `abstractify ui`, or `abstractify start`). On open, abstractify **backfills** missing vectors for entities that were created while `embed_mode` was `none`.

Model weights are cached under **`.abstractify/models`** (override with `ABSTRACTIFY_EMBED_MODEL_CACHE`). Default model: **`intfloat/multilingual-e5-large`**, **1024** dimensions. First embed may download weights; use `abstractify init --download-model` on a fresh project, or let the first backfill load the model.

To use a local HTTP embedding service (e.g. on port **7342**) instead of in-process FastEmbed, set `embed_mode = "rest"` and `embed_url = "http://127.0.0.1:7342/v1/embeddings"`, then restart the same way.
