# AuraPlayer — Modern Offline Native Audio Player

AuraPlayer is a native offline-first music player featuring a gorgeous, theme-adaptive design, continuous music playback with no silence between tracks, and comprehensive dynamic pages to easily explore your music collection.

---

## ⚠️ Project Status: In Development

AuraPlayer is **currently in progress and is not yet fully completed**. Core playback, library scanning, custom themes, and dynamic page navigation are completely functional. Secondary features like metadata editing, playlist modification, and the slide-out queue/lyrics panel are scheduled for subsequent roadmap steps.

🐛 **Found a bug?** Please report any issues or feedback in the **Issues** section of the repository!

---

## 🎨 What AuraPlayer Does Right Now

### 1. Dynamic Pages & Rich Navigation (Featuring Smart Multi-Artist Support)
* **Smart Multi-Artist Support:** Features an intelligent music organizer. It automatically splits collaborating artists (separated by characters or words like commas, ampersands, or "feat.") so that songs neatly appear under the individual profile of every contributing artist.
* **Artist Page:** Shows helpful statistics (like total track counts), a list of albums they released, a contributor section ("Appears On") for guest features, and a complete table of their tracks. Albums and guest features are laid out in a clean, wrapping grid that automatically resizes to fit your window, similar to photo grids on social media.
* **Album Page:** Displays a gorgeous view with large cover art, year of release, total duration, and clickable artist buttons. Tracks are automatically grouped by disc numbers. Additionally, track numbers morph into a play button when you hover, and transform into a lively dancing music equalizer during active playback.
* **Genre Page:** Displays songs filtered by selected genre, featuring instant play and shuffle controls.
* **Genres Tab:** A complete, alphabetically sorted list of all genres in your music library with track counts.
* **Aesthetic Tab Titles:** Dynamic pages display clean, professional titles like `Artist Name | Artist`, `Album Name | Album`, or `Genre Name | Genre`.
* **Smart Closable Tabs:** Dynamically opened pages can be closed with an "X" button, while permanent main navigation tabs (Tracks, Artists, Genres, Albums, Playlists) are securely locked in place.
* **Underlined Hover Feedback:** Hovering over artist or album names anywhere in the app displays elegant underlines with pointing-hand feedback; clicking them takes you directly to their dedicated pages.

### 2. Cover Art with Active Playback States in Tracks List
* Displays high-quality album covers or beautiful theme-matching fallbacks.
* **State A (PLAYING):** Cover art dims slightly and displays a beautiful, pulsing 3-bar animated equalizer.
* **State B (PAUSED + HOVER):** Cover art dims and displays an overlaid "▶" play icon.
* **State C (PAUSED + NO HOVER):** Cover art renders at full brightness with no overlays.

### 3. Advanced Audio Player Engine
* Plays popular music formats including `.mp3`, `.flac`, `.m4a`, `.wav`, and `.ogg` files.
* **Silence-Free Playback:** Automatically preloads the next song in the background to hand off seamlessly near the end of the current track, ensuring no silent gaps between songs.
* **Smart Music Controls:** Precise single-clicks for track skipping, press-and-hold for continuous fast-forward or rewind (seeking) inside a song, and a smart rewind button (restarts the current song if played past 3 seconds; otherwise skips to the actual previous song).
* **Remember Play State:** Automatically remembers your queue, active song, volume level, and exact listening position across restarts so you can resume listening instantly.
* **Volume & Output Selector:** Change your volume or choose headphones/speakers directly from the player screen. Settings are remembered across restarts, with an automatic fallback to the default device if headphones are unplugged. Includes an intuitive speaker icon that toggles quick muting and unmuting.

### 4. Smart Library Scanner & Secure Storage
* **Background Scanning:** Scans your selected music folders on a background worker with an elegant progress screen, meaning your app stays fast and responsive with absolutely no freezing.
* **Secure Storage Protection:** Automatically saves your library state safely, making sure a sudden computer shutdown or app crash never corrupts or loses your music collection.
* **Smart Duplication Prevention:** Automatically avoids duplicates when you rescan folders.
* **Missing File Safeguards:** If you delete or move a file outside the app, its row turns red in the Tracks list. Clicking it shows a helpful warning rather than crashing.

### 5. Personalization & Settings
* **Real-Time Themes:** Features immediate, single-click theme switching in Settings: **Dark (default)**, **Light**, **Midnight Blue**, and **Warm Amber**. The entire design updates instantly without needing to restart.
* **Custom Separation Manager:** In the settings screen, you can easily add, edit, or toggle the specific words or symbols (like commas or 'feat.') that AuraPlayer uses to split multiple artists, giving you ultimate control over how your library is organized.
* **Remembers Window Preferences:** AuraPlayer automatically remembers your window size, position, and layout preferences across restarts, so it always reopens exactly how you left it.

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
Install all required third-party libraries (including those for window styling and music file parsing) using pip:

```bash
pip install -r requirements.txt
```

### 4. Run the Application
Start the AuraPlayer application by executing the main script:

```bash
python main.py
```

---

## 🎵 Getting Started with Music

1. When you first launch AuraPlayer, your library will be empty.
2. Click the **⚙ (Settings)** icon in the top-right corner.
3. Click **Add Folder** and select the bundled `test_music/` folder (which contains 8 tagged test files of different formats) or point it at your real music library.
4. The progress dialog will show the scanning status. Once completed, your Tracks, Artists, Genres, and Albums tabs will be fully populated!
