# AuraPlayer — Step 3: Audio Playback Engine

*(Renamed from "Offline Music Player" to "AuraPlayer" on 2026-06-28.)*

## Changelog (this update — Step 3)

- **Added:** real audio playback via `PlaybackEngine`
  (`core/playback_engine.py`), built on PyQt6's `QMediaPlayer`. The
  bottom bar's Play/Pause/Next/Previous buttons (visually present since
  Step 2) are now fully functional, and double-clicking any track in
  the Tracks tab starts real playback.
- **Added:** gapless playback — the next track preloads silently in the
  background and hands off with no audible gap at ~95% of the current
  track's duration.
- **Added:** a real play queue with the exact behavior requested: no
  duplicate tracks ever; "Play Next" moves an already-queued track to
  right after the current one; "Add to Queue" moves it to the end;
  "Play All" replaces the whole queue.
- **Added:** repeat (off/all/one) and shuffle modes.
- **Added:** continuous position saving (~1s) plus exact saves on
  pause/stop, so closing and reopening the app resumes within about a
  second of where you left off — track, position, and queue are all
  restored, paused (not auto-playing).
- **Added:** a volume slider + output device selector
  (`VolumeOutputControl`), fully wired to the engine and persisted
  across restarts. This is a **per-app volume control** (like every
  media player's volume slider), not the Windows system/master volume
  — that distinction was confirmed before building; see
  `PROGRESS_LOG.md`'s Step 3 section for the full reasoning. The widget
  itself isn't visible anywhere yet — per spec it belongs on the Player
  Screen (Step 4), so it's built and tested now, ready to be placed
  into that screen's layout without rework.
- **Decided:** raw `.aac` files (bare streams with no container) will
  not be supported, after being briefly implemented and explicitly
  reverted — duration for that format can only ever be estimated, and
  it carries no metadata at all. `.mp3`, `.flac`, `.m4a`, `.wav`, `.ogg`
  remain the supported set.

## Previous update — Step 2

- **Added:** `PROGRESS_LOG.md` — tracks every roadmap step's status and
  actual deliverables, updated as the build progresses.
- **Added:** Theme Selector in Settings — Dark (default), Light,
  Midnight Blue, Warm Amber. Switching themes re-styles the entire app
  immediately, no restart needed, and the choice is remembered next
  time you open the app. Building this also surfaced and fixed two
  small theme-coverage bugs (the bottom-bar album-art placeholder and a
  couple of hint labels were still hardcoded to the dark theme's
  colors) so all 4 themes are now fully consistent everywhere.
- **Fixed:** the "Open Settings" button in the empty-state Tracks view
  did nothing when clicked. It now opens Settings exactly the same way
  the ⚙ gear icon does — both wire to the literal same method, so they
  can't drift apart in behavior again.
- **Redesigned:** the separator configuration UI. Instead of 5 checkboxes
  plus an unclear empty text box, Settings now shows every separator
  (default and custom) as a row with a checkbox to enable/disable it.
  Custom separators can be added (type + Add, or press Enter), edited
  (✎ button or double-click), and removed (✕ button). Default
  separators can be disabled but not deleted, so you can't accidentally
  lose all 5 with no way back.
- Added `FEATURE_BACKLOG.md` to the project — tracks all the feature
  ideas you sent (tab titles, full right-click menu, hover states,
  smart playlists, etc.) against which build step they naturally belong
  to, so none of them get lost between now and when their step arrives.

## What this step delivers

- The real PyQt6 application window for the first time — `python main.py`
  launches it.
- **Main/Menu screen**: top bar (Settings + Search), four tabs (Tracks,
  Artists, Albums, Playlists), and an always-visible bottom mini-player
  bar, per spec.
- **Tracks tab**: sortable table (Title/Artist(s)/Album/Duration),
  Play All + Shuffle buttons, right-click "…" menu with Edit Metadata /
  Remove Song / Add to Playlist. Remove Song is fully functional now;
  the other two show an in-app note about which later step builds them
  (so clicking them is informative, not a silent dead end).
- **Artists tab**: Artist Name + Track Count, alphabetically sorted.
  Track count includes every track an artist contributed to (lead or
  featured).
- **Albums tab**: Album Name, Artists, total Duration, Year. Albums are
  grouped by album name + primary album artist, so two different
  artists' "Greatest Hits" don't merge into one.
- **Playlists tab**: correct empty state; full playlist management
  arrives in Step 7.
- **Settings dialog**: Add/Remove music folders (triggers a real
  background scan), artist separator checkboxes + custom separator
  field, matching your spec exactly.
- **Threaded scanning**: folder scans run on a background `QThread`
  with a progress dialog, so the UI never freezes — even on a very
  large library.
- **Live sync, no restart needed**: removing a track, adding a folder,
  or any other library mutation goes through `LibraryStore`, which
  emits Qt signals that every tab listens to. I specifically tested
  this: removing a track updates the Tracks table, the Albums list
  (dropping an album that's now empty), and the Artists list (dropping
  an artist with zero tracks left) — automatically, with no manual
  refresh call and no app restart.
- **Missing-file handling**: a track whose file disappears shows in red
  in the Tracks list; clicking it shows the exact message from your
  spec instead of crashing.
- A deliberate dark theme (not default Qt grey) — see `ui/theme.py` for
  the full palette if you want to tweak colors before I build more
  screens on top of it.

## New project structure (on top of Step 1)

```
musicplayer/
├── core/
│   ├── library_store.py      # NEW: Qt-signal observer layer over LibraryCache
│   └── ... (Step 1 files, unchanged)
├── ui/
│   ├── theme.py               # Color palette + stylesheet
│   ├── main_window.py         # Top bar + tabs + bottom bar
│   ├── scan_worker.py         # Background QThread for folder scanning
│   ├── models/
│   │   ├── tracks_table_model.py      # Backs the Tracks table
│   │   ├── library_group_models.py    # Album/Artist grouping + models
│   │   └── playlists_list_model.py
│   ├── views/
│   │   ├── tracks_view.py
│   │   ├── artists_view.py
│   │   ├── albums_view.py
│   │   └── playlists_view.py
│   └── widgets/
│       ├── top_bar.py
│       ├── bottom_bar.py
│       ├── settings_dialog.py
│       ├── scan_progress_dialog.py
│       └── empty_state.py
├── main.py                    # <-- RUN THIS for the real app
├── smoketest.py                # Automated screenshot-based UI test (dev tool)
├── test_threaded_scan.py       # Automated test of the real threaded scan path
└── step1_demo.py               # Still works, unchanged, for console-only testing
```

## How to run it

### 1. Install dependencies (same as Step 1, nothing new)

```bash
pip install -r requirements.txt
```

### 2. Launch the app

```bash
python main.py
```

On first launch every tab shows its empty state — that's correct.

### 3. Add the bundled test folder (or your own real music)

Click the ⚙ (Settings) button, top-right → **Add Folder** → select the
`test_music/` folder bundled in this project (or point it at your real
music library). A progress dialog appears while it scans in the
background, then all four tabs populate.

### 4. Things worth specifically trying

- **Live sync**: with the library populated, right-click a track →
  Remove Song → confirm. Watch the Artists and Albums tabs — if that
  was the only track for an artist or album, they disappear immediately
  with no restart.
- **Missing file**: close the app, rename or move one file out of your
  music folder, reopen the app, and re-add/rescan the same folder via
  Settings. That track should show in red in the Tracks tab; clicking
  it shows the "file is missing" message instead of crashing.
- **Multiple folders**: add a second folder in Settings and confirm
  both scans merge into one library without duplicating anything you'd
  already scanned.
- **Resize the window** and try a very long artist/album name to check
  text doesn't overflow awkwardly.
- **Theme switching**: open Settings → change "App theme" → the whole
  app (including this Settings dialog) re-colors immediately. Close
  and reopen the app — your choice should still be applied.
- **Playback (new in Step 3)**: double-click any track in the Tracks
  tab. It should start playing and show up in the bottom bar with a
  thin progress strip along the top edge. Try Play All / Shuffle at the
  top of the Tracks tab too.
- **Restart recovery**: play a track, let it run a few seconds, then
  close the app entirely and reopen it. It should resume the same
  track at roughly the same position, paused (you'll need to press
  play yourself — it won't auto-resume audibly).
- **Queue behavior**: right-click isn't wired to the queue actions yet
  (that's the full Queue Panel in Step 8), but you can exercise the
  underlying logic by checking `library_cache.json`'s `player_state.queue`
  after using Play All — it should always be track paths with no
  duplicates.

### 5. Automated tests I ran (you can re-run these yourself)

```bash
# Verifies the real background QThread scan path (signals, cache persistence)
python test_threaded_scan.py

# Generates screenshots of every tab/state into _screenshots/ for visual review
python smoketest.py
```

## A note on what's intentionally not working yet

Clicking a track, Play All, Shuffle, Edit Metadata, Add to Playlist,
and the Search button all show a small "coming in Step X" dialog
instead of doing nothing silently. That's deliberate — the playback
engine, Player Screen, Artist/Album pages, metadata editing, and
playlists are all still ahead in the roadmap. If any of those dialogs
fire where you *didn't* expect them to (i.e. you thought something
should already work), that's useful feedback — let me know.

## What to check / give feedback on

- Does the dark theme look right to you, or would you prefer a
  different accent color / lighter theme? Easy to change now, in one
  file (`ui/theme.py`), before more screens are built on top of it.
- Try it against your real library (not just the 8 test files) and see
  if the Tracks/Artists/Albums tabs look right at real scale.
- Any column you'd want reordered, resized differently, or added/removed
  in the Tracks/Albums tables?
- Settings dialog: anything missing, or does folder add/remove feel
  right?

Once you're happy with this, next up is **Step 3: audio playback engine
+ functional bottom-bar transport controls** — the riskiest technical
piece, tackled in isolation per the roadmap, before the full Player
Screen UI in Step 4.

