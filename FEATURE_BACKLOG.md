# Feature Backlog

Features requested that don't fit the *current* step, tracked here so
they survive across the whole build rather than living only in chat
history. Each gets implemented when the step it naturally belongs to
arrives, and gets checked off + dated here when done.

## 1. Tab titles show type
**Status:** ✅ COMPLETED

"Travis Scott | Artist", "Rodeo | Album", "My Favorites | Playlist"
on dynamically-opened tabs.
**Fits:** Step 5 (Artist/Album pages) + Step 7 (Playlists), since that's
when dynamic tabs first exist.

## 2. Right-click menu — full version with icons
Play Next, Add to Playing Queue, Edit Metadata, Remove Song,
Add to Playlist (submenu of playlists), Properties (full info dialog:
art, all tags, bitrate, sample rate, file path/size/format).
**Fits:** Spread across Step 3 (queue exists → Play Next/Add to Queue),
Step 6 (Edit Metadata), Step 7 (Add to Playlist submenu), and a
Properties dialog can land alongside Step 6 since it needs the same
tag-reading path as the editor.

## 3. Left-click behavior on rows
**Status:** ✅ COMPLETED

Click artist name -> open "Name | Artist" tab (underline on hover).
Click album name -> open "Name | Album" tab (underline on hover).
Click elsewhere on row -> play track.
**Fits:** Step 5, when Artist/Album pages exist to navigate to.

## 4. Album cover displayed on the left side of track name in the menu/track list
**Status:** ✅ COMPLETED

This feature displays the track's album cover thumbnail on the left side of the track name in the tracks list, with three dynamic visual states depending on playback and hover states:

- **State A - Current song is PLAYING:**
  - Show an animation with 3 bars moving up and down (like a chart/equalizer)
  - Reduce album cover brightness (darker appearance)
- **State B - Current song is PAUSED + Cursor HOVER:**
  - Show a play icon (▶) overlaid on the album cover
  - Reduce album cover brightness (darker appearance)
- **State C - Current song is PAUSED + No Hover:**
  - Show the album cover in normal state (full brightness, no overlay)

## 5. Lyrics panel — Edit Lyrics button
**Status:** ✅ COMPLETED

✏️ button at the bottom of the lyrics panel in both synced and
non-synced modes. Opens a full-featured code-style `LyricsEditorDialog` with disk persistence.

## 6. Search bar redesign
Remove standalone 🔍 button; replace with a live search INPUT FIELD
directly in the top bar next to ⚙. Filters current tab + related tabs
in real time across Track/Artist/Album/Playlist name, including on
dynamic tabs (Artist/Album/Playlist pages).
**Fits:** Step 9 (Search), but the top-bar layout change should happen
when Step 9 starts so we're not redesigning the top bar twice.

## 7. Smart playlists (4 fixed, non-removable)
Recently Added 🕐, Favorites ❤️, Recently Played 🔄, Most Played 🔥.
Each has its own sort logic and can't be deleted by the user.
**Fits:** Step 7 (Playlists). Note: Recently Played and Most Played need
a `last_played` timestamp and `play_count` on Track -- adding those
fields to the model is a small Step 3 addition (playback engine is what
would update them) so Step 7 doesn't need a model migration later.

## 8. Stats header on every tab/page
"Total Tracks: XXX" / "Total Artists: XXX" / etc., plus per-page counts
("Tracks by this artist: XXX") on Artist/Album/Playlist pages.
**Fits:** Cheap to add incrementally as each view/page is built --
Tracks/Artists/Albums/Playlists tabs can get this in a small Step 2
follow-up; Artist/Album/Playlist pages get it natively when built in
Steps 5/7.

## 9. Drag & drop, full support
Tracks -> Playlists, between playlists, reordering the Queue, dragging
folders into the app to add to library.
**Fits:** Step 7 (playlist drag-drop + reordering, already specced),
Step 3/8 (queue reordering), and folder drag-drop can be added to the
Settings folder list or main window whenever Step 7 is in progress.

## 10. Favorite (heart) toggle for tracks
❤️ in two places: next to the currently-playing track (bottom bar /
Player Screen) and in the bottom panel next to Lyrics & Queue buttons.
Toggling adds/removes from the Favorites smart playlist (see #7).
**Fits:** Step 4 (Player Screen) for the screen-level heart, Step 7 for
the Favorites-playlist wiring (depends on #7 existing first).

## 11. Export Library (Settings)
Button in Settings to export all track data (path, metadata, play
count, last played, etc.) as JSON or CSV.
**Fits:** Late step, once play count / last played exist (depends on
#7's model additions) -- naturally a Settings addition once the rest of
Settings is stable, likely alongside or after Step 9.

## 12. Volume control (Player Screen, bottom right)
**Status:** ✅ COMPLETED

A volume slider in the Player Screen, opposite side from the other
bottom controls.

**Important correction on scope:** the request describes this as
controlling the **system/master volume** via `QAudioDevice`. That's not
something Qt's audio APIs can do -- `QAudioDevice` only enumerates
output devices and reports their capabilities; it has no method to
change the OS-level master volume, and neither does any other
cross-platform Qt class. Every desktop media player's in-app volume
slider (Spotify, VLC, etc.) controls that **app's own playback volume**
via its audio engine (e.g. `QMediaPlayer.setVolume()` / the Step 3
playback engine's own gain control) -- the OS volume mixer is a
separate, OS-specific layer.

If true system/master volume control (changing the Windows volume mixer
itself, affecting every app) is genuinely wanted rather than just
per-app playback volume, that needs a Windows-specific library
(`pycaw`, which wraps the Windows Core Audio API) bolted on as an
optional extra -- it won't be cross-platform and adds a real dependency.
**Default plan, unless told otherwise:** build this as a standard
per-app playback volume slider (the normal, expected behavior for a
volume control inside a media player), and treat true OS-master-volume
control as a separate optional add-on if still wanted once you see the
normal version in action.
**Fits:** Step 3 (playback engine needs a volume/gain control regardless
of which flavor is chosen) for the engine method, Step 4 (Player Screen)
for the actual slider UI.

## 13. Output device selector (Player Screen, next to volume)
**Status:** ✅ COMPLETED

Dropdown/button to choose which audio output device to play through
(speakers, headphones, etc.), using `QAudioDevice` to enumerate the
system's available output devices -- this part of the original request
*is* accurate; device enumeration and selection is exactly what
`QAudioDevice` (Qt6's replacement for the deprecated `QAudioDeviceInfo`)
is for.
**Fits:** Step 3 for the engine-level "list devices + set active output
device" methods, Step 4 (Player Screen) for the dropdown UI next to the
volume slider.

## 14. Queue panel in the Main Menu top bar (slide-in, resizable)
**Status:** ✅ COMPLETED

A 📋 Queue button in the Main Menu top bar, positioned between Settings
(⚙) and Search (🔍). Opens a panel that:
- Slides in from the right with a smooth animation
- Takes a portion of the width, not the full screen -- the tabs/content
  area resizes to make room rather than being covered
- Has an explicit "✕" close button that slides it back out

This is functionally the same Queue panel as the one already planned
for the Player Screen (Step 8) -- same underlying queue data and the
same panel widget, just exposed as a second, independent entry point
from the Main Menu's top bar in addition to the Player Screen's bottom
controls. Both entry points stay in sync automatically.

## 15. Gapless playback
**Status:** ✅ COMPLETED

Pre-load the next track at ~95% completion of the current one, so there's
no audible silence/gap between tracks -- important for concept albums
and continuous mixes.
**Fits:** Step 3 (Audio Playback Engine) -- this is genuinely an engine-
level concern (needs a second `QMediaPlayer`/`QAudioOutput` pair primed
and ready to swap in at the boundary), so it belongs in the same step as
the rest of the playback engine rather than bolted on later.

## 16. Dynamic ambient background (Player Screen only)
Extract prominent colors from the currently-playing track's album art
and render a soft, blurred gradient halo behind the Player Screen.
Explicitly NOT applied to the Main Menu/tabs screens -- those stay
minimal.
**Fits:** Step 4 (Player Screen), since the album art is front-and-center
there for the first time and this is purely a Player-Screen-only visual
treatment.

## 17. Global smooth transitions
Qt-based animations (QPropertyAnimation or similar) for every tab
switch, click, selection, and state change across the whole app --
no instant/rigid UI changes anywhere.
**Fits:** Cross-cutting rather than one step -- most naturally applied
incrementally as each screen is built (Steps 4 onward), since retrofitting
animations onto already-built static widgets means touching everything
twice. Step 4's Player Screen is the first place this would show up
concretely (album art transitions, lyrics/queue panel slides).

## 18. Custom transport controls + smart Next/Prev behavior
**Status:** ✅ COMPLETED

Replace the current placeholder emoji buttons (▶ ⏮ ⏭) with proper
anti-aliased SVG/vector icons matching AuraPlayer's styling. Plus:
- Long-press Next/Prev fast-forwards/rewinds (seeks) through the
  current track at accelerated speed, vs. a single click jumping
  tracks
- Smart Prev: clicking Previous while a track is playing restarts the
  CURRENT track from 0:00, unless playback is within the first few
  seconds (in which case it actually goes to the previous track) --
  this matches the behavior most people expect from phone/car media
  controls
**Fits:** Step 3 (engine-level: the seek-while-held logic and the
"how many seconds counts as 'just started'" threshold are playback-
engine concerns) + Step 4 (Player Screen, where the new icon assets
and press-and-hold interaction actually get wired to real buttons) +
Step 2's bottom bar transport buttons get the same icon treatment
applied retroactively once the icons exist.

## 19. Smart Play Queue drag-and-drop reordering
**Status:** ✅ COMPLETED

Drag tracks within the Queue panel to reorder the active playing
queue. Custom-designed `QueueListWidget` automatically updates the
active playing sequence inside `PlaybackEngine` on drop.

## 20. Karaoke-style lyrics panel (with sync recovery)
**Status:** ✅ COMPLETED

- Album art fades out / lyrics fade in
- Active line highlighted/enlarged with smooth animation; inactive
  lines dimmed
- Manual scrolling is always allowed; if it diverges from playback
  position, a floating "Sync" button appears and smoothly animates the
  view back to the current line when clicked

## 21. App header branding + animated tab indicator
- Top bar shows "AuraPlayer" + an app icon, loaded from
  `assets/logo.png` -- the UI code should reference this path but NOT
  generate/placeholder the actual image file; the person will place a
  real transparent PNG there themselves.
- Tab menu (Tracks/Artists/Albums/Playlists): the faint static
  underline becomes a full-width base line across the whole tab
  container, with a separate, distinctly-highlighted active-tab
  indicator segment that smoothly slides/animates when switching tabs.
**Fits:** Step 9, bundled with the Search redesign since both touch the
same `TopBar`/tab-area widgets and code -- doing the logo+indicator
work now and the Search-bar layout change later would mean two separate
passes over the same small piece of UI. The plain text rename to
"AuraPlayer" (no logo, no animated indicator yet) was already applied
on 2026-06-28 as a safe, contained change; the icon asset and the
animated indicator itself remain here, pending Step 9.

## 22. Multiple Genres support
A `genres` field (list of strings, parsed with the same separator logic
as `artists`) plus a full Genres tab, a dynamic Genre page, a Tracks-view
Genre column, Edit Metadata support, search inclusion, and a View menu
toggle. Full spec as given:

- **Data model:** `Track.genres: list[str]`, parsed from the existing
  single `genre` tag field using `split_artists()` (already general-
  purpose despite the name) with the same configured separators.
  **Implementation note:** the current `genre` reader in
  `metadata_reader.py` uses `_first_or_default()` (collapses to the
  first tag value), the exact same pattern that caused the original
  artist multi-value bug fixed earlier in this project. Reading
  `genres` correctly will need the `_artist_list_or_default()`-style
  fix applied to genre tags too, across all formats (MP3/FLAC/M4A/WAV/
  OGG), not just a new field added on top of the old single-value read.
  **Open question to confirm before implementing:** the separator list
  includes `"feat."`, which makes sense for artists but reads oddly for
  genres (a tag like `"Pop feat. Rock"` isn't a realistic genre string).
  Plan is to reuse the exact same active-separator list for genres
  unless told otherwise -- flagging so this isn't a silent assumption.
- **Genres tab** (list + count, A-Z default sort, "Total Genres: XXX"
  stat): ✅ COMPLETED in Step 5 (a new tab between Artists and Albums).
- **Genre page** (dynamic tab, same shape as a Tracks-view list, "Tracks
  in this genre: XXX" stat): ✅ COMPLETED in Step 5 (click a name, get a filtered track list).
- **Tracks view Genre column** (after Album, before Duration): a
  straightforward column addition to the existing `TracksTableModel`.
- **Edit Metadata Genres field:** ✅ COMPLETED in Step 6 (fully supports multi-genre editing with tags and chip inputs).
- **Search inclusion:** depends on the Step 9 search redesign (item #6)
  existing first -- genres become one more field the live search
  matches against.
- **View menu with show/hide checkboxes:** this is a new piece of UI
  that doesn't exist yet anywhere in the app (there's currently no
  "View" menu at all, just the Tracks/Artists/Albums/Playlists tab bar
  itself) -- needs to be introduced as part of this feature rather than
  slotted into something pre-existing.

**Fits:** Split across steps by sub-part rather than one single step,
since this feature's pieces depend on different parts of the roadmap
that don't all exist yet:
  - `genres` model field + scanner/reader fix → Step 3-adjacent data
    work, but safe to do as its own small contained step whenever
    convenient since it doesn't depend on anything else listed here
  - Genres tab + Tracks-view Genre column → alongside Step 2's tab
    infrastructure (a "Step 2.5"-style addition) since both reuse
    patterns Step 2 already established and don't need Step 4+ to exist
  - Genre page (dynamic tab) → Step 5, alongside Artist/Album pages,
    since all three are "click a name, get a filtered track list" pages
    sharing the same dynamic-tab mechanism
  - Edit Metadata Genres field → Step 6, with the rest of the metadata
    editor
  - Search inclusion + View menu → Step 9, alongside the search redesign
    and other top-bar/menu work

---

## 23. Automatic Folder Sync Mechanism
**Status:** ✅ COMPLETED

Implement a Git-like automatic synchronization mechanism for added folders:
- Save metadata (.music-sync.json) in the app directory to store file lists, timestamps, and change logs.
- Scan for changes (adds, deletes, edits) automatically on startup and every 30 seconds.
- Provide a "Sync Now" manual trigger button in the Settings > Add Folder section.
- Gracefully handle deleted or missing folders by prompting the user to Delete (remove from library) or Resync (try again), looping if the folder remains unreachable.
- Red-highlight missing files (fully integrated with existing danger styling).
- Lock the app with an ApplicationModal progress dialog during the first-time scanning/importing of a newly added folder to prevent race conditions or invalid states.
- Fully atomic-style change logs to seamlessly resume interrupted scans when the app is restarted.

---

## Future ideas (explicitly deferred past v1, no step assigned)
- Album-based accent coloring
- Mini Player
- Similar tracks recommendation
- Dark/Light mode toggle
- Playback speed control
- Custom themes
