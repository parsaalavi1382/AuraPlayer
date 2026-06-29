"""
Generates small test audio files (silent tones, ~2 seconds) across multiple
formats with embedded metadata, so we can verify the scanner/reader end to
end against real files rather than mocks.

Run once: python generate_test_files.py
"""

import os
import subprocess

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, TDRC, TPOS, TRCK, APIC
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis

OUT_DIR = os.path.join(os.path.dirname(__file__), "test_music")


def make_silent_audio(path: str, duration: float = 2.0):
    """Use ffmpeg to generate a silent audio file of the right container type."""
    ext = os.path.splitext(path)[1].lower()
    codec_args = {
        ".mp3": ["-c:a", "libmp3lame"],
        ".flac": ["-c:a", "flac"],
        ".m4a": ["-c:a", "aac"],
        ".wav": ["-c:a", "pcm_s16le"],
        ".ogg": ["-c:a", "libvorbis"],
    }[ext]
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", str(duration), *codec_args, path,
        ],
        check=True, capture_output=True,
    )


def tiny_png_bytes() -> bytes:
    """A minimal valid 1x1 PNG, used as fake embedded album art."""
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
        "53de0000000c4944415408d76360000000020001e221bc330000000049454e"
        "44ae426082"
    )


def tag_mp3(path, title, artist, album, album_artist, year, disc, track, with_art=True):
    audio = MP3(path, ID3=ID3)
    audio.delete()
    audio.tags = ID3()
    audio.tags.add(TIT2(encoding=3, text=title))
    audio.tags.add(TPE1(encoding=3, text=artist))
    audio.tags.add(TALB(encoding=3, text=album))
    audio.tags.add(TPE2(encoding=3, text=album_artist))
    audio.tags.add(TDRC(encoding=3, text=year))
    audio.tags.add(TPOS(encoding=3, text=str(disc)))
    if track is not None:
        audio.tags.add(TRCK(encoding=3, text=str(track)))
    if with_art:
        audio.tags.add(APIC(encoding=3, mime="image/png", type=3, desc="cover", data=tiny_png_bytes()))
    audio.save()


def tag_flac(path, title, artist, album, album_artist, year, disc, track, with_art=True):
    audio = FLAC(path)
    audio["title"] = title
    audio["artist"] = artist
    audio["album"] = album
    audio["albumartist"] = album_artist
    audio["date"] = year
    audio["discnumber"] = str(disc)
    if track is not None:
        audio["tracknumber"] = str(track)
    if with_art:
        pic = Picture()
        pic.data = tiny_png_bytes()
        pic.type = 3
        pic.mime = "image/png"
        audio.add_picture(pic)
    audio.save()


def tag_m4a(path, title, artist, album, album_artist, year, disc, track, with_art=True):
    audio = MP4(path)
    audio["\xa9nam"] = [title]
    audio["\xa9ART"] = [artist]
    audio["\xa9alb"] = [album]
    audio["aART"] = [album_artist]
    audio["\xa9day"] = [year]
    audio["disk"] = [(disc, 0)]
    if track is not None:
        audio["trkn"] = [(track, 0)]
    if with_art:
        audio["covr"] = [tiny_png_bytes()]
    audio.save()


def tag_ogg(path, title, artist, album, album_artist, year, disc, track, with_art=True):
    audio = OggVorbis(path)
    audio["title"] = title
    audio["artist"] = artist
    audio["album"] = album
    audio["albumartist"] = album_artist
    audio["date"] = year
    audio["discnumber"] = str(disc)
    if track is not None:
        audio["tracknumber"] = str(track)
    # Skipping embedded art for OGG test file -- METADATA_BLOCK_PICTURE
    # encoding isn't essential to validate for Step 1's scope.
    audio.save()


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    test_files = [
        # (filename, tagger, title, artist_raw, album, album_artist, year, disc, track)
        ("track1.mp3", tag_mp3, "Sunset Drive", "Aria Vance", "Night Sessions", "Aria Vance", "2021", 1, 1),
        ("track2.mp3", tag_mp3, "Midnight Echo", "Aria Vance & Leo Park", "Night Sessions", "Aria Vance", "2021", 1, 2),
        ("track3.mp3", None, None, None, None, None, None, 0, None),  # deliberately untagged MP3
        ("track4.flac", tag_flac, "Glass Horizon", "Mira Cole, Theo Banks", "Reflections", "Mira Cole", "2019", 1, 1),
        ("track5.m4a", tag_m4a, "Paper Boats", "Jonah Reyes feat. Aria Vance", "Paper Boats EP", "Jonah Reyes", "2022", 1, 1),
        ("track6.wav", None, None, None, None, None, None, 0, None),  # untagged WAV (WAV tagging is unreliable; test untagged path)
        ("track7.ogg", tag_ogg, "Static Bloom", "Theo Banks", "Reflections", "Mira Cole", "2019", 1, 2),
        # Second disc, to test disc-number grouping/sorting on the Album page later
        ("track8.flac", tag_flac, "Afterglow", "Mira Cole", "Reflections", "Mira Cole", "2019", 2, 1),
    ]

    for fname, tagger, title, artist_raw, album, album_artist, year, disc, track in test_files:
        path = os.path.join(OUT_DIR, fname)
        make_silent_audio(path)
        if tagger is not None and title is not None:
            tagger(path, title, artist_raw, album, album_artist, year, disc, track)
        print(f"Created {fname}" + (" (tagged)" if tagger and title else " (untagged)"))

    print(f"\nDone. {len(test_files)} test files in {OUT_DIR}")


if __name__ == "__main__":
    main()
