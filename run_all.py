#!/usr/bin/env python3
"""
Batch Pipeline Runner for Alumni Band Music
Executes flip_folder_tool across all 19 instrument booklets with their custom manifests.
"""

import glob
import os
import time

from flip_folder_tool import process_packet

SOURCE_DIR = "/Users/josumi/Downloads/Alumni Band Music"
MANIFEST_DIR = "manifests"

instruments = [
    "Alto 1", "Alto 2", "Baritone", "Bass Drum",
    "Clarinet 1", "Clarinet 2", "Cymbals",
    "Flute 1", "Flute 2", "French Horn",
    "Snare", "Tenor Drums", "Tenor Sax",
    "Trombone 1", "Trombone 2",
    "Trumpet 1", "Trumpet 2", "Trumpet 3", "Tuba"
]

def main():
    t_start = time.time()
    print("=" * 70)
    print(f"Starting batch extraction for all {len(instruments)} instruments...")
    print("=" * 70)
    
    summary = []
    
    for i, inst in enumerate(instruments, 1):
        pdf_path = os.path.join(SOURCE_DIR, f"{inst}.pdf")
        manifest_path = os.path.join(MANIFEST_DIR, f"{inst}_arrangements.json")
        
        if not os.path.exists(pdf_path):
            print(f"[Warning] Missing PDF: {pdf_path}")
            continue
        if not os.path.exists(manifest_path):
            print(f"[Warning] Missing manifest: {manifest_path}")
            continue
            
        print(f"\n>>> [{i:02d}/{len(instruments)}] Starting {inst}...")
        t0 = time.time()
        process_packet(
            pdf_path=pdf_path,
            manifest_path=manifest_path,
            instrument_name=inst,
            jobs=8,
            force=False
        )
        elapsed = time.time() - t0
        summary.append((inst, elapsed))
        
    total_elapsed = time.time() - t_start
    print("\n" + "=" * 70)
    print(f"ALL {len(instruments)} INSTRUMENTS PROCESSED IN {total_elapsed:.1f}s")
    print("=" * 70)
    for inst, el in summary:
        out_dir = os.path.join(SOURCE_DIR, inst)
        master_pdf = os.path.join(SOURCE_DIR, f"{inst} - ALL.pdf")
        chart_count = len(glob.glob(os.path.join(out_dir, "*.pdf")))
        size_mb = os.path.getsize(master_pdf) / (1024 * 1024) if os.path.exists(master_pdf) else 0.0
        print(f"  {inst:<15}: {chart_count} charts in folder | Master: {size_mb:.1f} MB ({el:.1f}s)")

if __name__ == "__main__":
    main()
