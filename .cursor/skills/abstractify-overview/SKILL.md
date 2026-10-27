---
name: abstractify-overview
description: >-
  Карта текущего Abstractify: архитектура, модули, CLI и формат вывода, граф,
  эмбеддинги, UI, MCP, AGENTS.md и init. Использовать, когда нужно понять или
  менять abstractify, не перечитывая src/abstractify и docs с нуля.
---

# Abstractify — как устроено сейчас

Пакет хранит **графы абстракций**, которые пишет агент (или человек через CLI/UI). Живой источник правды — SQLite рядом с целевым проектом. JSON-файлы графов — только спутниковый дамп после записи. MCP и UI читают ту же базу.

Два вида графа: `structural` и `flow`. Принцип абстракции не зашит: его задаёт пользователь и он хранится в поле `principle` графа.

## Где что лежит

Код пакета — `src/abstractify/`:

| Модуль | Роль |
|---|---|
| `cli.py` | argparse, команды, JSON в stdout |
| `store.py` | SQLite: чтение, запись, поиск, путь, explain |
| `schema.sql` | таблицы |
| `config.py` | `.abstractify/config.toml`, порты, лимиты |
| `project.py` | `init`, блок в `AGENTS.md`, копия скилла |
| `mcp_server.py` | MCP-инструменты поверх `Store` |
| `ui_server.py` | Starlette: `/api/*` и статика `ui/dist` |
| `embeddings/` | режимы `none`, `local`, `rest`, `custom` |
| `size.py` | отказ, если граф слишком большой |
| `skills/always-on.md` | текст, который `init` вставляет в `AGENTS.md` |
| `skills/SKILL.md` | скилл, который `init` копирует в целевой проект |
| `ui/` | React + D3/SVG; в пакет попадает собранный `dist` |

После `abstractify init` в **целевом** проекте:

```
.abstractify/config.toml
.abstractify/abstractify.db
.abstractify/graphs/<id>.json
.abstractify/snapshots/<id>.json
.cursor/skills/abstractify/SKILL.md
AGENTS.md    # блок <!-- abstractify:begin --> … <!-- abstractify:end -->
```

Три процесса могут делить одну базу (WAL): CLI, `serve`, `ui`.

## Граф

- **Сущность** (`entities`): `name`, `description`. Может входить в несколько графов (`graph_entities`).
- **Привязка к коду** (`code_refs`): путь и необязательный диапазон строк. По ней работает обратный индекс «файл → абстракции».
- **Ребро** (`edges`): `source_id`, `target_id`, строка `relation`, `kind` (`structural` | `flow` | `meta`), JSON `metadata`. Отдельного флага «двустороннее» нет: два направления — два ребра. Готового поля entry/exit нет; вход и выход видны только по топологии.
- **Мета-связь** (`meta_links`): связь между сущностями вне обычных рёбер графа, в том числе между графами.
- **Снимок** (`snapshots`): JSON одного графа на момент времени.

Словарь отношений не закрыт. В схеме названы кандидаты `knows_about`, `does_not_know_about`, `calls`, `responds_to`; CLI и MCP принимают любую строку.

Лимиты по умолчанию (`config.toml`): 80 сущностей и 200 рёбер на граф. Выше — отказ, пока не передан `confirm_large`. Жёсткий потолок — 500 сущностей.

Каждая успешная запись обновляет `.abstractify/graphs/<id>.json`. Истина всё равно в SQLite.

## Эмбеддинги

Режим в `embed_mode`. Поиск **всегда** считает текстовый IDF. Векторная часть добавляется, только если режим не `none`.

| Режим | Что делает |
|---|---|
| `none` | Только текст. Векторов нет. |
| `local` | FastEmbed в процессе. Модель по умолчанию `intfloat/multilingual-e5-large`, 1024 измерения. Нужен `pip install 'abstractify[local]'`. Кэш весов: `.abstractify/models`. |
| `rest` | HTTP `POST {"texts":[...], "input_type": "document"\|"query"}`. URL по умолчанию `http://127.0.0.1:7342/v1/embeddings`. Ключ — переменная `ABSTRACTIFY_EMBED_API_KEY`, не конфиг. |
| `custom` | Свой Python-файл с `embed(texts)` и необязательным `retrieve`. |

Включить позже, не переинициализируя проект: `abstractify embeddings enable --mode local|rest`. Без `--no-backfill` сразу досчитывает недостающие векторы. Отдельная команда — `abstractify embeddings backfill`. После смены конфига перезапускают `serve` / `ui` / `start`.

## CLI

Корень почти у всех команд — путь к проекту (позиционный аргумент или `--path`, по умолчанию `.`). `abstractify --version` печатает версию.

Успешный результат команд, которые отдают данные, — **один JSON-объект в stdout**, отступ 2 пробела, без текста вокруг. Флага `--json` нет. Ошибки (`FileNotFoundError`, `ValueError`, `KeyError`) — обычный текст в **stderr**, код 1. Слишком большой граф — JSON ошибки в stdout, код 2.

| Команда | Поведение | stdout при успехе |
|---|---|---|
| `init [PATH]` | Создаёт `.abstractify/`, конфиг, базу, скилл, блок `AGENTS.md`. `--embed-mode` (`none` по умолчанию), `--embed-url`, `--embed-model`, `--custom-adapter`, `--force`, `--example`, `--download-model` (только с `local`). | JSON с портами |
| `init --only-agents` | Только переписывает блок в `AGENTS.md` из текущего шаблона. Конфиг, базу и скилл не трогает. Если проект не инициализирован — ошибка в stderr. | JSON с портами уже существующего конфига |
| `serve [PATH]` | MCP. `--transport stdio` (по умолчанию) или `http`. `--host` по умолчанию `127.0.0.1`. `--port 0` берёт `mcp_port` из конфига. | stdio — протокол MCP; http — процесс uvicorn |
| `ui [PATH]` | Веб-UI. `--port 0` берёт `ui_port`. `--open` открывает браузер. Хост только loopback. | JSON `{"ok","url","root"}` |
| `start [PATH]` | Вместе HTTP MCP и UI. Сам гаснет после `--timeout` секунд без запросов (3600). `--always-on` отключает простой. | Текст о старте в stderr |
| `status [PATH]` | Проверяет serve и UI на портах конфига. | Текст `connected` или `disconnected` |
| `embeddings enable --mode local\|rest` | Пишет `embed_mode`. `--url`, `--no-backfill`. | JSON |
| `embeddings backfill` | Векторы для сущностей без них. | JSON |
| `affected [FILES...] [--git] [--path]` | Абстракции по файлам. Сам граф не меняет. Без файлов и без `--git` — stderr `No files given...`, код 1. | JSON: `files`, `entities`, `graphs`, `note` |
| `search QUERY [-k 20]` | Текст + семантика, если эмбеддинги включены. | JSON: `query`, `mode`, `hits` |
| `path SOURCE TARGET [--graph] [--directed]` | Кратчайший путь. Без `--directed` рёбра двусторонние для поиска. Корень — флаг `--path`. | JSON: `source`, `target`, `found`, `nodes`, `edges`. Нет пути — тот же JSON с `"found": false` |
| `explain ENTITY` | Сущность, соседи, рёбра, графы. | JSON: `entity`, `neighbors`, `edges`, `graphs` |
| `graph list [--kind structural\|flow]` | Список графов. | JSON |
| `graph get ID` | Один граф. Нет id — stderr `graph not found`. | JSON |
| `graph create --name --kind --principle [--description] [--from-json] [--confirm-large]` | Новый граф. | JSON |
| `graph update ID [...]` | Правка. `--from-json` заменяет состав. | JSON |
| `graph delete ID` | Удаление. | JSON `{"ok": true\|false}` |
| `entity list [--query] [--graph]` | Список сущностей. | JSON |
| `entity upsert --name [--description] [--graph] [--id] [--code-ref path[:start[:end]]]` | Создать или обновить. `--code-ref` можно повторять. | JSON |
| `snapshot create GRAPH_ID [--label]` | Снимок. | JSON |
| `snapshot list [--graph]` | Список снимков. | JSON |

Восстановление снимка есть в MCP (`restore_snapshot`), отдельной CLI-команды нет.

## MCP

`abstractify serve` поднимает `MCPServer`. Инструменты вызывают `Store` и не читают JSON-дампы. Успех: `{"ok": true, "data": ...}`. Ошибка: `{"ok": false, "error", "message"}`. Слишком большой граф — словарь `GraphTooLarge`.

Инструменты: `list_graphs`, `get_graph`, `create_graph`, `update_graph`, `delete_graph`, `list_entities`, `get_entity`, `upsert_entity`, `delete_entity`, `upsert_edge`, `delete_edge`, `add_meta_link`, `delete_meta_link`, `lookup_by_file`, `affected_by_files`, `search`, `path`, `explain`, `create_snapshot`, `list_snapshots`, `get_snapshot`, `restore_snapshot`.

Вшитая инструкция сервера: абстракции решает агент; после правки кода не переписывать граф автоматически; сначала `affected_by_files` или `lookup_by_file` и проверка; на каждый граф записывать принцип; большой граф — спросить пользователя, затем `confirm_large=true`.

Stdio для Cursor: `abstractify serve /абсолютный/путь/к/проекту`. HTTP: `abstractify serve --transport http`, endpoint `/mcp`.

## UI

`abstractify ui` отдаёт собранный `src/abstractify/ui/dist` и API той же базы. Пересборка: `npm install` и `npm run build` в `src/abstractify/ui`.

Экран: слева список графов (фильтр all / structural / flow) и вкладка сущностей; холст — SVG. Карточка вершины: имя и три счётчика (файловые ссылки, степень, мета-связи). Клик по карточке открывает описание и связи. Клик по пустому холсту снимает выбор.

- **structural:** силовая раскладка D3, карточки перетаскиваются, рёбра — прямые между центрами.
- **flow:** рёбра — кубические Безье от границы карточки к границе (горизонтальные контрольные точки). Перетаскивания нет, выбор — кликом. Позиции по-прежнему считает силовая модель, отдельные колонки по шагам не заданы.
- Направление ребра: стрелки каждые 100 px вдоль пути или бегущие точки диаметром 6 px. Переключатель **Arrows / Dots** и клавиша `A`. Режим пишется в `localStorage` ключом `abstractify.edgeMotion`. Отдельного цвета для входа и выхода нет: палитра — бирюза, жёлтый у выбранной вершины, приглушённый зелёный у соседей.

## AGENTS.md и init

`init` делает по порядку: выделяет свободные порты UI и MCP, пишет `config.toml`, открывает базу, при `--example` сеет пример, копирует `skills/SKILL.md` в `.cursor/skills/abstractify/SKILL.md`, вставляет в `AGENTS.md` блок из `skills/always-on.md` плюс строки с портами.

Маркеры блока: `<!-- abstractify:begin -->` и `<!-- abstractify:end -->`. Повторный `init` без `--force` падает с `FileExistsError`. `--only-agents` на уже инициализированном проекте заново пишет только этот блок (порты берутся из текущего конфига) и не трогает базу, конфиг и файл скилла.

Смысл блока для агента в целевом проекте: Abstractify — основной способ ориентироваться, не запасной. По теме сначала `search`, по файлам — `path` или `lookup_by_file`. Новые абстракции агент предлагает сам, но не записывает молча. После правки кода — `affected`, сверка, без автоизменения графа. `init` агент сам не запускает. Если `status` показывает disconnected, можно запустить `abstractify start`.
