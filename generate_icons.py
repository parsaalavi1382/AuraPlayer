#!/usr/bin/env python3
"""
AuraPlayer Multi-Resolution Icon Generator
Reads 'assets/logo.png' and outputs high-quality multi-layered 'logo.ico' and 'logo.icns'.
Requires Pillow (pip install Pillow).
"""

import os
import sys

def generate_icons():
    try:
        from PIL import Image
    except ImportError:
        print("Error: Pillow library is not installed. Please install it using 'pip install Pillow'.", file=sys.stderr)
        sys.exit(1)

    project_dir = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(project_dir, 'assets', 'logo.png')
    ico_path = os.path.join(project_dir, 'assets', 'logo.ico')
    icns_path = os.path.join(project_dir, 'assets', 'logo.icns')

    if not os.path.exists(png_path):
        print(f"Error: Master PNG not found at {png_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading master PNG from {png_path}...")
    img = Image.open(png_path)

    # Ensure we have RGBA mode for transparency support
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    # Resolve lanczos resampling filter for different Pillow versions
    try:
        resample_filter = Image.Resampling.LANCZOS
    except AttributeError:
        # Compatibility for older Pillow versions
        resample_filter = Image.ANTIALIAS

    print("Generating multi-layer logo.ico (Windows)...")
    # ICO supports standard sizes: 16x16, 32x32, 48x48, 64x64, 128x128, 256x256
    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format='ICO', sizes=ico_sizes)
    print(f"Successfully saved high-quality multi-layer ICO to: {ico_path}")

    print("Generating multi-layer logo.icns (macOS)...")
    # ICNS supports powers of two sizes: 16x16, 32x32, 64x64, 128x128, 256x256, 512x512, 1024x1024
    icns_sizes = [(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)]
    img.save(icns_path, format='ICNS', sizes=icns_sizes)
    print(f"Successfully saved high-quality multi-layer ICNS to: {icns_path}")

    print("Icon automation complete! All platform assets are ready.")

if __name__ == '__main__':
    generate_icons()
