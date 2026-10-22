# SmartPark native desktop rebuild

Research and implementation date: 19 October 2026.

## Scope and interpretation

This implements the latest request: research established desktop applications, then rebuild **native desktop presentation only**. Here, “before AI” means source releases from 2021, before the recent generative-AI development boom. It does not mean that AI did not exist, or prove that a particular contributor never used AI.

The earlier production-stabilization document is background, not authorization to continue changing the engine during this UI task. Existing stabilization changes were preserved. No services, recognition algorithms, media transports, API contracts, payment workflows, authentication routines, database schemas, launch/service management, or hardware command handlers were rewritten.

Research used the requested Chrome browser for official visual references, the connected GitHub tool for historical source, and web search for release history and Qt accessibility documentation. Current screenshot galleries illustrate layout patterns; **historical claims are grounded in the pinned source versions**, not assumed from current screenshots. No third-party source code, artwork, or icons were copied into SmartPark.

## Historical references and lessons

### DB Browser for SQLite — v3.12.2

The official history dates the original application to 2003 and v3.12.2 to 18 May 2021. Its desktop workspace prioritizes a conventional menu/toolbar, task tabs, resizable data views, and secondary inspection panes rather than a web-style landing screen. [Official history](https://sqlitebrowser.org/about/), [official visual reference](https://sqlitebrowser.org/).

The historical build is C++11, Qt5 Widgets, and CMake, with explicit Qt modules and test options. Its Designer file separates widget composition from behavior, uses named actions, and gives task tabs accessible names. A dedicated `SqliteTableModel` owns table-data behavior rather than encoding all database logic into widgets. [Build definition](https://github.com/sqlitebrowser/sqlitebrowser/blob/v3.12.2/CMakeLists.txt), [window composition](https://github.com/sqlitebrowser/sqlitebrowser/blob/v3.12.2/src/MainWindow.ui), [table model](https://github.com/sqlitebrowser/sqlitebrowser/blob/v3.12.2/src/sqlitetablemodel.h).

Applied: a stable window shell, task-oriented navigation, adjustable table columns, conventional menus, and explicit widget names. SmartPark's existing row-to-record mappings remain intact; adding sorting without a corresponding model migration would risk selecting the wrong underlying record, so sorting was deliberately not enabled.

### KeePassXC — 2.6.6

The release announcement dates this version to 11 June 2021. The official gallery shows a navigation tree, a primary record list, a detail region, and discoverable menus/search. The gallery is a current visual reference, not a timestamped image of 2.6.6. [Release announcement](https://keepassxc.org/blog/2021-06-11-2.6.6-released/), [screenshots](https://keepassxc.org/screenshots/).

Historical source uses Qt Designer window composition, stacked workspaces, reusable actions shared with context menus, a find shortcut, and saved window geometry/state. The source/build organization distinguishes `core`, `crypto`, `format`, and `gui`; the GUI further separates database tabs, search, previews, settings, and widgets. These boundaries matter more than copying its appearance. [Main window implementation](https://github.com/keepassxreboot/keepassxc/blob/2.6.6/src/gui/MainWindow.cpp), [window definition](https://github.com/keepassxreboot/keepassxc/blob/2.6.6/src/gui/MainWindow.ui), [source/build organization](https://github.com/keepassxreboot/keepassxc/blob/2.6.6/src/CMakeLists.txt).

Applied: page search with Ctrl+K, a toolbar reusing the existing Refresh and Help actions, local appearance/window/sidebar preferences, and lazy page creation. Display preferences are separate from site configuration and do not persist camera ownership or gate selections.

### qBittorrent — release-4.3.9

The official release history dates v4.3.9 to 31 October 2021. Its source is useful for studying maintainability in a long-lived desktop utility rather than borrowing torrent-specific workflows. [Official release history](https://www.qbittorrent.org/news).

The historical CMake source separates `base`, optional `gui`, `webui`, and application composition. The GUI has a dedicated target and individual models, delegates, property widgets, dialogs, and status-bar components. Its transfer-list model declares named columns and data roles. [Source composition](https://github.com/qbittorrent/qBittorrent/blob/release-4.3.9/src/CMakeLists.txt), [GUI target](https://github.com/qbittorrent/qBittorrent/blob/release-4.3.9/src/gui/CMakeLists.txt), [transfer model](https://github.com/qbittorrent/qBittorrent/blob/release-4.3.9/src/gui/transferlistmodel.h).

Applied: separate window chrome, presentation helpers, and visual tokens from API-backed page workflows. A complete model/view migration is deferred because it would change data handling during the requested engine freeze.

## Accessibility conclusions

An old desktop application is not automatically accessible. Source inspection establishes useful mechanisms, not conformance or real screen-reader usability. Qt recommends scalable interfaces, keyboard operation, meaningful text, and use of accessible standard widgets; labels can provide a buddy relationship for field focus. [Qt accessibility guidance](https://doc.qt.io/qt-6/accessible.html), [QLabel buddy behavior](https://doc.qt.io/qt-6/qlabel.html#buddy).

Implemented in SmartPark:

- Persistent username/password labels, field buddies, and a default sign-in action; authentication and first-run credential handling are unchanged.
- Keyboard page search with Ctrl+K; Enter/Down opens a matching page, Escape clears the filter, and F1 exposes the existing shortcut help.
- Explicit names for navigation, forms, camera selectors, live pictures, evidence images, zoom controls, report contents, and record tables.
- Clearly visible focus styling and non-color-only text labels.
- System, Light, Dark, and High contrast appearances; enabled body, muted, and selected text token pairs are checked for at least 4.5:1 contrast.
- Point-based text-size controls from 10 to 18 points, plus scrollable workspaces for larger text and smaller windows.
- Read-only record tables, alternating rows, keyboard row selection, and user-resizable columns. User column widths survive theme/text-size changes within the session.

Limitations: token contrast checks do not certify every rendered control or dynamic legacy status label. Custom video overlays and existing drag-to-draw detection zones are not newly made keyboard-operable. System mode follows the application's captured native palette, not a newly implemented OS-theme-change listener. Native Windows high-DPI, NVDA, and high-contrast interoperability still require field validation.

## Implemented architecture

- `app/desktop/shell.py`: native window chrome, navigation filtering, page context, menus/toolbar, text size, and local `QSettings` display preferences. No API or service imports.
- `app/desktop/presentation.py`: accessible field labels, form presentation, table presentation, scalable label typography, and scrollable page containers. No API or service imports.
- `app/desktop/theme.py`: shared color tokens, Qt palette application, and presentation styles. Defaults are restrained, neutral, thin-bordered native utility styling rather than making every button a primary action.
- `app/desktop/main.py`: existing permission-driven page registration and page workflows retained; shell composition delegates to the new modules. Live gate command buttons now precede the video so they do not sit below long evidence panels. Device actions use two rows instead of an overflowing single row. Session controls have persistent labels and a compact vertical action area.
- `app/desktop/desk.py`: report selectors and report actions are separate rows, with field labels and a useful report empty state. Report, export, print, and backup request handlers are unchanged.
- `tests/test_desktop_presentation.py`: fixture-only Qt interaction/rendering checks; site writes and all hardware/command requests are prohibited by the fixture client.

This is a presentation-boundary refactor, not a claim that the existing 3,000-line page/controller module has been completely decomposed. Moving API-backed page workflows, changing worker ownership, or replacing their data models would enlarge the engine regression surface and is intentionally outside this change.

### Preferences and startup

Appearance, text size, sidebar proportions, and window geometry are stored under the local Qt settings identity `SmartPark / OperatorDesktop`. No credentials or site settings are stored there. A previously saved window geometry is reused; the first launch retains the existing maximized-window default. Navigation remains permission-filtered using the existing backend manifest. No camera page is automatically restored on startup.

## Validation and reproducibility

Use the existing development environment; no new runtime packages were added:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q \
  tests/test_desktop_presentation.py tests/test_display_mailbox.py \
  tests/test_live_gates_ui.py tests/test_ui_productization.py \
  -k 'not test_ui_docs_exist'
```

The new UI tests exercise lazy navigation/filter indexes, keyboard page finding, shared action identity/dispatch, label semantics, read-only tables, display preference isolation, palette contrast, theme synchronization, preserved user column widths, manual control placement, text-size limits, overflow scrolling, and fixture-only rendering. Existing display-mailbox and desktop UI contract checks are included without running the engine.

Result: **22 passed, 1 deselected**, plus successful Python compilation and `git diff --check`.

The separately run `test_ui_docs_exist` fails because the repository already lacks `docs/ui/UI-ARCHITECTURE.md` and related legacy productization documents. Those unrelated documents were absent before this task; this rebuild does not fabricate them to make that check pass.

A pre-edit SHA-256 baseline was taken of 421 existing versioned/non-ignored files. Compared with that baseline, only `app/desktop/main.py`, `app/desktop/desk.py`, and `app/desktop/theme.py` changed. All other existing files, including untested stabilization work, are byte-for-byte preserved. An AST comparison of `main.py` also confirms that existing API call expressions and non-presentation runtime methods are unchanged. New files are presentation helpers, UI tests, this document, and fixture preview images.

Generate the preview images without launching services or connecting hardware:

```bash
QT_QPA_PLATFORM=offscreen \
SMARTPARK_UI_PREVIEW_DIR=research/desktop-ui/previews \
  .venv/bin/pytest -q tests/test_desktop_presentation.py
```

### Fixture previews

These are explicitly labeled fixture renders, not evidence of functioning live cameras or a production-ready engine:

- [Dashboard — light, 1280×800](research/desktop-ui/previews/dashboard-light.png)
- [Live Gates — light, 1280×900](research/desktop-ui/previews/live-gates-light.png)
- [Sessions — light, 1024×768](research/desktop-ui/previews/sessions-light.png)
- [Reports — dark, 1280×900](research/desktop-ui/previews/reports-dark.png)
- [Settings — high contrast, 1024×768](research/desktop-ui/previews/settings-high-contrast.png)

## Before deployment

1. On Windows, verify 100%, 150%, and 200% display scaling; keyboard-only login/navigation; long labels; and all role-specific pages.
2. Check NVDA announcements, focus order, native high-contrast behavior, and manual commands with an authorized operator.
3. Test page switching while real video is running and confirm the unchanged live-stream cleanup behavior.
4. Perform the separate pending engine/hardware acceptance tests before making any production-readiness claim. This UI work did not perform them.
