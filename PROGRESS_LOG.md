# 🎵 AuraPlayer - Development Progress Log

*(Project renamed from "Music Player" to "AuraPlayer" on 2026-06-28.)*

## 📊 Overall Status

| Stage | Status | Completed |
|-------|--------|-----------|
| Step 1 | ✅ Done | 2026-06-28 |
| Step 2 | ✅ Done | 2026-06-28 |
| Step 3 | ✅ Done | 2026-06-29 |
| Step 4 | 🔜 Planned | - |
| Step 5 | 🔜 Planned | - |
| Step 6 | 🔜 Planned | - |
| Step 7 | 🔜 Planned | - |
| Step 8 | 🔜 Planned | - |
| Step 9 | 🔜 Planned | - |
| Step 10 | 🔜 Planned | - |

---

## 📋 Detailed Step Log

### ✅ Step 1: Folder Scanner + JSON Cache
**Status:** Done
**Date:** 2026-06-28
**Deliverables:**
- Recursive folder scanner supporting MP3, FLAC, M4A, WAV, OGG
- Per-format metadata reader normalized into one `Track` model (title,
  artists, album, album artists, year, genre, disc number, track
  number, embedded-art detection), despite each format storing tags
  completely differently under the hood (ID3 vs Vorbis comments vs MP4
  atoms)
- Multi-artist splitting using configurable separators, including the
  fix for Windows-style multi-value artist tag lists (e.g.
  `["Travis Scott", "Future", "2 Chainz"]`) instead of only reading the
  first entry
- JSON cache with **atomic writes** (temp file + `os.replace`, so a
  crash mid-save can't corrupt the library)
- Dedup by file path on re-scan (never creates duplicate entries)
- Missing-file detection — a file deleted/moved outside the app gets
  flagged `file_missing: true` instead of crashing the scanner, and
  un-flags itself if the file reappears
- `step1_demo.py` console script + `generate_test_files.py` (creates 8
  real tagged audio files across all 5 formats for testing)

### ✅ Step 2: Main Window UI (Tracks/Artists/Albums/Playlists)
**Status:** Done
**Date:** 2026-06-28
**Deliverables:**
- Real PyQt6 application window (`main.py`) — Main/Menu screen with top
  bar (Settings + Search), four tabs, and an always-visible bottom
  mini-player bar
- `LibraryStore`: Qt-signal observer layer over the JSON cache. Every
  view subscribes to its signals (`tracks_added`, `track_updated`,
  `track_removed`, etc.) so the UI updates live with **no manual
  refresh and no app restart** — verified by removing a track and
  confirming Tracks, Albums, and Artists views all updated automatically
- Tracks tab: sortable table (Title/Artist(s)/Album/Duration, default
  A-Z), Play All + Shuffle buttons, right-click menu (Edit Metadata /
  Remove Song / Add to Playlist — Remove Song fully functional, the
  other two correctly say which later step builds them)
- Artists tab: Artist Name + Track Count (counts every track an artist
  contributed to, lead or featured)
- Albums tab: Album Name, Artists, total Duration, Year — grouped by
  album name + primary album artist so same-named albums by different
  artists don't merge
- Playlists tab: correct empty state (full management is Step 7)
- Settings dialog: Add/Remove music folders (triggers a real background
  scan with a progress dialog), separator management
- Threaded scanning on a background `QThread` so the UI never freezes,
  even on very large libraries
- Missing-file rows render in red in the Tracks list; clicking one
  shows the correct warning instead of crashing
- `QAbstractTableModel`/`QAbstractListModel`-backed views throughout
  (not one widget per row), so the UI stays fast regardless of library
  size
- A deliberate dark theme (`ui/theme.py`) rather than default Qt styling
- **Bugfix:** "Open Settings" button in the empty state now opens
  Settings — wired to the exact same method as the ⚙ gear icon
- **Redesign:** separator configuration is now a full list with
  checkboxes (enable/disable without losing the separator), add via
  input+button/Enter, edit (✎) and remove (✕) for custom separators;
  default separators can be disabled but not deleted
- `FEATURE_BACKLOG.md` added to track requested features against the
  step they naturally belong to
- **Theme Selector**: Settings now has a theme dropdown (Dark, Light,
  Midnight Blue, Warm Amber) that re-applies the global stylesheet
  immediately and persists across restarts — see "Cross-Cutting
  Additions" below for details
- **Planned follow-up (not yet built):** a Genres tab will be added
  alongside Tracks/Artists/Albums/Playlists, following the same
  Artists-tab pattern — see `FEATURE_BACKLOG.md` item #22. Logged here
  rather than under Step 5+ since it reuses Step 2's existing tab
  infrastructure directly and doesn't depend on later steps.

### ✅ Step 3: Audio Playback Engine
**Status:** Done
**Date:** 2026-06-29
**Deliverables:**
- `PlaybackEngine` (`core/playback_engine.py`) built on `QMediaPlayer`/
  `QAudioOutput`: play, pause, stop, seek, smart Previous (restarts the
  current track unless within the first ~3 seconds, in which case it
  goes to the actual previous track — `FEATURE_BACKLOG.md` item #18),
  Next
- **Gapless playback** (`FEATURE_BACKLOG.md` item #15): two
  `QMediaPlayer`/`QAudioOutput` pairs are kept at all times (active +
  silent standby preloaded with whatever plays next); handoff happens
  at 95% of the active track's duration with no audible gap. Volume and
  output device are kept in sync across both players so the handoff
  never causes a volume jump or device reversion.
- **Queue management**, exactly per the specified logic: the queue is
  unique by track path (no duplicates ever). "Play Next" moves an
  already-queued track to right after the current one rather than
  duplicating it; "Add to Queue" moves it to the end. Play All replaces
  the queue entirely, never appends. Verified with a test that
  specifically exercises "play_next/add_to_queue on the
  currently-playing track itself" — this caught and fixed a real bug
  where the current-track index could desync after such a move.
- Repeat modes (off/all/one) and shuffle, both tested for correct
  behavior at queue boundaries (stop vs. wrap vs. stay)
- **Continuous (~1s) position persistence** plus exact-position saves
  on every pause/stop, so a restart resumes within ~1 second of where
  playback last was — verified via a real simulated-restart test (one
  engine instance saves, a second fresh instance reloads the same cache
  and restores track + position correctly, paused not auto-playing)
- **Volume control**: per-app playback volume (not OS master volume —
  see the decision below), persisted across restarts via a new
  `PlayerState.volume` field
- **Output device selector**: `QMediaDevices`/`QAudioDevice`
  enumeration and selection, also persisted across restarts via a new
  `PlayerState.output_device_id` field (falls back silently to the
  system default if a previously-selected device is no longer present
  — e.g. headphones unplugged — rather than erroring)
- `VolumeOutputControl` widget (`ui/widgets/volume_output_control.py`):
  volume slider + output device dropdown, fully wired to the real
  engine (tested end-to-end: dragging the actual slider updates the
  actual engine and persists to disk) but deliberately not placed in
  any layout yet — per spec these controls belong on the Player Screen
  (Step 4), not the Main Menu, so it's built and ready for Step 4 to
  simply place rather than build from scratch
- Bottom bar (from Step 2) is now fully functional: Play/Pause/Next/
  Previous buttons drive real playback, a thin progress strip along the
  top edge reflects real position, and the play/pause icon reflects
  real state
- **Volume control scope decision:** the original ask described
  system/master volume via `QAudioDevice`. That's not something Qt's
  audio APIs can do — see `FEATURE_BACKLOG.md` item #12 for the full
  explanation. Built as standard per-app playback volume (how every
  media player's volume slider actually works), confirmed with the
  person before building.
- **Playback engine library decision:** `QMediaPlayer` (PyQt6.QtMultimedia),
  confirmed by directly testing it against all 8 test files across all 5
  supported formats in this sandbox — all loaded with correct duration
  and zero errors, on Qt's modern FFmpeg-based multimedia backend (not
  the older GStreamer backend responsible for most of `QMediaPlayer`'s
  negative reputation online).
- **Decision: raw `.aac` (bare ADTS stream, no container) will NOT be
  supported** (decided 2026-06-28, after briefly being implemented and
  then explicitly reverted at the person's request). It does play
  correctly via `QMediaPlayer`/mutagen, but its duration can only be
  estimated from bitrate (confirmed via direct testing — FFmpeg itself
  logs "Estimating duration from bitrate, this may be inaccurate" for
  these files) and it carries no metadata tags at all (no container to
  store them). Supported formats remain exactly: `.mp3`, `.flac`,
  `.m4a`, `.wav`, `.ogg`. (Note: `.m4a` is unaffected by this decision —
  it's AAC audio inside a proper MP4 container, which has a real
  duration index and tag storage, unlike bare `.aac`.) May be revisited
  in a future version per the person's note.

### 🔜 Step 4: Player Screen
**Status:** Planned
**Deliverables:**
- [Placeholder — full Player Screen: album art, progress bar with
  click-to-seek, transport controls, lyrics panel toggle, queue panel
  toggle, More menu, Favorite (❤️) toggle. The volume slider + output
  device selector (`VolumeOutputControl`, bottom-right per spec) are
  ALREADY BUILT and fully wired to the engine as of Step 3 — this step
  just needs to place the existing widget in the Player Screen's
  layout, not build it from scratch — see `FEATURE_BACKLOG.md` items
  #10, #12, #13]

### 🔜 Step 5: Album Page + Artist Page + Genre Page
**Status:** Planned
**Deliverables:**
- [Placeholder — dedicated Album Page (grouped by disc number), Artist
  Page (Albums / Appears On / full track list), and Genre Page (same
  list shape as Tracks view, filtered to one genre, "Tracks in this
  genre: XXX" stat — see `FEATURE_BACKLOG.md` item #22), plus clickable
  artist/album/genre navigation everywhere in the app, with dynamic tab
  titles ("Name | Artist" / "Name | Album" / "Name | Genre")]

### 🔜 Step 6: Metadata Editing
**Status:** Planned
**Deliverables:**
- [Placeholder — Edit Metadata dialog writing changes back to the
  actual audio file via mutagen, with live cache + UI refresh across
  all views; includes a Genres field alongside Artists, using the same
  separator-based multi-value entry — see `FEATURE_BACKLOG.md` item #22]

### 🔜 Step 7: Playlists
**Status:** Planned
**Deliverables:**
- [Placeholder — create/rename/delete playlists, add/remove tracks,
  drag-and-drop reordering, cover image picker]

### 🔜 Step 8: Queue Panel + Lyrics Panel
**Status:** Planned
**Deliverables:**
- [Placeholder — queue panel UI (slide-in from the right, splitter-
  style draggable left edge with min/max width clamps, "X" close
  button), accessible from BOTH the Player Screen and a new 📋 Queue
  button in the Main Menu top bar between Settings and Search — same
  panel widget and queue data, two entry points — see
  `FEATURE_BACKLOG.md` item #14; lyrics panel with the album-art-slides
  -left animation and synced-lyrics support]

### 🔜 Step 9: Settings Polish + Search
**Status:** Planned
**Deliverables:**
- [Placeholder — live search across Tracks/Artists/Albums/Playlists/
  Genres (search matches genre names too, filtering the Genres tab the
  same way it filters the others — see `FEATURE_BACKLOG.md` item #22),
  search bar moved directly into the top bar replacing the standalone
  🔍 button; app header branding (logo from `assets/logo.png` + title,
  already showing "AuraPlayer" as text) and the animated sliding
  active-tab indicator — see `FEATURE_BACKLOG.md` item #21; new View
  menu with show/hide checkboxes for each tab including Genres (this is
  a new menu, nothing like it exists yet)]

### 🔜 Step 10: Packaging
**Status:** Planned
**Deliverables:**
- [Placeholder — installation instructions, finalized `requirements.txt`,
  possible PyInstaller `.exe` build]

---

## 🎨 Cross-Cutting Additions

- **Project renamed to "AuraPlayer"** (2026-06-28): updated in the
  window title, the Main Menu top-bar header, and this log's own title
  plus `README.md`'s header. No code module names changed (the project
  folder, internal class names, etc. were never named after the old
  "Music Player" title to begin with, so this was a low-risk, contained
  rename).
- **Theme Selector** (requested 2026-06-28, delivered 2026-06-28): ✅ Done.
  Settings now has a theme dropdown — Dark (default), Light, Midnight
  Blue, Warm Amber. Switching applies the new stylesheet to the whole
  app immediately (no restart), and the choice persists across
  restarts. Building this surfaced two real theme-coverage bugs (the
  bottom-bar album-art placeholder and two hint labels had hardcoded
  dark-theme colors baked in) which are now fixed so all 4 themes are
  fully consistent everywhere in the app, not just in the main color
  areas.
- **Top bar layout change** (requested 2026-06-28, scheduled for Step 8):
  the Main Menu top bar (currently `[Settings ⚙]` on the right with
  Search 🔍 next to it, from Step 2) will gain a 📋 Queue button
  positioned between them: `[⚙] [📋] [🔍]`. Noted here now so the
  change doesn't surprise anyone comparing Step 8's top bar to Step 2's
  screenshots — the underlying `TopBar` widget gets a new button added,
  not rebuilt from scratch.
- See `FEATURE_BACKLOG.md` for the full list of 11 additional features
  requested during Step 2 review (tab titles, full right-click menu,
  hover states, smart playlists, drag & drop, favorites, export, etc.)
  and which step each is scheduled for.
