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

    # Crop any transparent margins so the logo fills the entire icon canvas nicely
    bbox = img.getbbox()
    if bbox:
        print(f"Trimming transparent margins from bounding box: {bbox}...")
        cropped_img = img.crop(bbox)
        
        # Now, make the cropped image a perfect square by padding it with transparency 
        # to preserve its original aspect ratio instead of stretching or distorting it
        w, h = cropped_img.size
        max_dim = max(w, h)
        
        # Create a new square transparent canvas
        square_img = Image.new("RGBA", (max_dim, max_dim), (0, 0, 0, 0))
        # Paste the cropped image centered
        paste_x = (max_dim - w) // 2
        paste_y = (max_dim - h) // 2
        square_img.paste(cropped_img, (paste_x, paste_y))
        img = square_img
        print(f"Re-centered and squared image to {max_dim}x{max_dim}")

    # Resolve lanczos resampling filter for different Pillow versions
    try:
        resample_filter = Image.Resampling.LANCZOS
    except AttributeError:
        # Compatibility for older Pillow versions
        resample_filter = Image.ANTIALIAS

    print("Generating multi-layer logo.ico (Windows)...")
    # ICO supports standard and high-DPI scaling sizes: 16, 24, 32, 48, 64, 96, 128, 256
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (96, 96), (128, 128), (256, 256)]
    
    # Save with modern PNG compression for high compatibility and light file sizes in Win 10/11
    img.save(ico_path, format='ICO', sizes=ico_sizes, bitmap_format='png')
    print(f"Successfully saved high-quality multi-layer ICO to: {ico_path}")

    print("Generating multi-layer logo.icns (macOS)...")
    # ICNS supports powers of two sizes: 16, 32, 64, 128, 256, 512, 1024
    icns_sizes = [(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)]
    img.save(icns_path, format='ICNS', sizes=icns_sizes)
    print(f"Successfully saved high-quality multi-layer ICNS to: {icns_path}")

    print("Icon automation complete! All platform assets are ready.")

if __name__ == '__main__':
    generate_icons()
