#!/usr/bin/env python3
"""
Default runner for Clarinet 1 flip folder extraction.
Calls the generalized flip_folder_tool pipeline with default parameters.
"""
from flip_folder_tool import process_packet

if __name__ == "__main__":
    process_packet(
        pdf_path="Clarinet 1.pdf",
        manifest_path="arrangements.json",
        output_dir="Extracted_5x7_Charts",
        master_pdf_path="Clarinet_1_Complete_5x7_FlipFolder.pdf",
        instrument_name="Clarinet 1"
    )
