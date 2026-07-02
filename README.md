# AuraPlayer — Modern Offline Native Audio Player

AuraPlayer is a native offline-first music player built with Python and PyQt6, featuring a gorgeous, theme-adaptive user interface, gapless audio playback, and comprehensive dynamic navigation pages (Artist, Album, and Genre pages).

---

## ⚠️ Project Status: In Development

AuraPlayer is **currently in progress and is not yet fully completed**. Core playback, library scanning, custom themes, and dynamic page navigation are completely functional. Secondary features like metadata editing, playlist modification, and the slide-out queue/lyrics panel are scheduled for subsequent roadmap steps.

🐛 **Found a bug?** Please report any issues or feedback in the **Issues** section of the repository!

---

## 🎨 What AuraPlayer Does Right Now

### 1. Dynamic Pages & Rich Navigation (Featuring Smart Multi-Artist Support)
* **Smart Multi-Artist & Separator Support:** Features an intelligent music library organizer. It automatically parses common artist separators (like `,`, `&`, `feat.`, `ft.`) to split tracks and neatly display them under the individual profile of each contributing artist, keeping your collection perfectly organized.
* **Artist Page:** Dedicated view showing stats, list of albums released by the artist, contributor/guest tracks ("Appears On"), and a complete track table.
* **Album Page:** Gorgeous custom album details view. Displays large cover art, stats, release year, and album artists (clickable buttons). Tracks are automatically grouped by disc number (perfect for multi-disc releases).
* **Genre Page:** Dynamically filters tracks by selected genre, featuring instant "Play Genre" and "Shuffle" controls.
* **Genres Tab:** Alpha-sorted main list of all genres in your music library with track counts.
* **Aesthetic Tab Titles:** Newly opened dynamic pages display clean, professional titles like `Artist Name | Artist`, `Album Name | Album`, or `Genre Name | Genre`.
* **Smart Closable Tabs:** Dynamic tabs are equipped with an "X" close button, while permanent core navigation tabs (Tracks, Artists, Genres, Albums, Playlists) are locked in place.
* **Underlined Hover & Interactivity:** Hovering over artist or album names anywhere in the app displays elegant underlines with pointing-hand feedback; clicking them takes you directly to their dedicated pages.

### 2. Cover Art with Active Playback States in Tracks List
* Tracks list displays high-quality embedded album covers (or custom theme-adaptive placeholders).
* **State A (PLAYING):** Covers dim slightly and display a beautiful, dynamically-pulsing 3-bar equalizer animation.
* **State B (PAUSED + HOVER):** Covers dim and display an overlaid "▶" play icon.
* **State C (PAUSED + NO HOVER):** Covers render at full brightness with no overlays.

### 3. Solid Audio Playback Engine (Gapless Audio Player)
* Built on PyQt6's `QMediaPlayer` with a modern FFmpeg backend supporting `.mp3`, `.flac`, `.m4a`, `.wav`, and `.ogg`.
* **Gapless Playback:** Preloads the upcoming track in a secondary background player to hand off seamlessly at ~95% duration with no audible gap. Perfect for continuous audio files and live albums.
* **Smart Transport Controls:** Precise single-clicks for track-skipping, press-and-hold for continuous scrubbing, and "Smart Prev" (restarts the track if played past 3 seconds, otherwise skips to the actual previous track).
* **Persistent Play State:** Automatically remembers your queue, active track, and exact playback position (within ~1 second accuracy) across restarts so you can resume listening instantly.
* **Output Device & Volume Persistence:** Change volume or choose headphones/speakers directly from the Player Screen. Settings are remembered across restarts, with graceful fallback to the default device if headphones are unplugged.

### 4. Background Threaded Scanner & JSON Cache
* Folder scanner runs entirely on a background `QThread` multi-threaded scanner with an elegant progress dialog so the UI never freezes.
* Uses **atomic writes** (`os.replace`) to prevent database corruption during writes.
* Performs intelligent deduplication and handles missing files gracefully (missing files turn red in the Tracks list; clicking them alerts the user instead of crashing).

### 5. Adaptive Aesthetic Themes
* Features immediate, single-click theme switching in Settings: **Dark (default)**, **Light**, **Midnight Blue**, and **Warm Amber**.
* The entire stylesheet re-renders in real-time without requiring a restart, and your selection is saved.

---

## 🚀 Installation & Setup

Follow these simple steps to set up a clean Python virtual environment, install the required packages, and run AuraPlayer.

### 1. Create a Virtual Environment (`venv`)
Creating a virtual environment ensures AuraPlayer's dependencies do not conflict with other Python packages on your system.

* **On Windows / macOS / Linux:**
    ```bash
    python -m venv venv
    ```

### 2. Activate the Virtual Environment
Before installing packages or running the app, you must activate the virtual environment.

* **On Windows (Command Prompt):**
    ```cmd
    venv\Scripts\activate.bat
    ```
* **On Windows (PowerShell):**
    ```powershell
    venv\Scripts\activate.ps1
    ```
* **On macOS / Linux (Terminal):**
    ```bash
    source venv/bin/activate
    ```

*(Once activated, you will see `(venv)` prepended to your command line prompt.)*

### 3. Install Dependencies
Install all required third-party libraries (including `PyQt6` and `mutagen`) using pip:

```bash
pip install -r requirements.txt
4. Run the Application
Start the AuraPlayer application by executing the main script:

Bash
python main.py
🎵 Getting Started with Music
When you first launch AuraPlayer, your library will be empty.

Click the ⚙ (Settings) icon in the top-right corner.

Click Add Folder and select the bundled test_music/ folder (which contains 8 tagged test files of different formats) or point it at your real music library.

The progress dialog will show the scanning status. Once completed, your Tracks, Artists, Genres, and Albums tabs will be fully populated!
