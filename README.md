# FlipFolder-Parser

**Automated marching band sheet music parser and flip-folder standardizer.**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](LICENSE)
![Output: 5x7 Landscape](https://img.shields.io/badge/format-5%22%C3%977%22%20Landscape-orange.svg)
![Platform: macOS | Windows | Linux](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey.svg)

---

## What is FlipFolder-Parser?

Marching band music is traditionally printed as **2-up half-sheets** (two songs per standard 8.5" × 11" page). When scanned or distributed digitally, these packets often suffer from:

- **Crooked scans** and tilted staves.
- **Binder punch holes**, dark margins, and dividing cut lines.
- **Tiny publisher copyright fine print** taking up precious vertical space.
- **Handwritten or boxed performance cuts** that players easily miss while marching.
- **Multi-page tunes** split across different pages.

**FlipFolder-Parser** is an automated tool that takes raw marching band section packets and converts them into:

1. **Individual 5" × 7" landscape PDFs** for every single arrangement, perfectly proportioned for physical flip-folder plastic windows and tablet viewers (ForScore, MobileSheets, GoodNotes, etc.).
2. **A compiled master flip-folder PDF** containing all charts in performance order.
3. **Multi-page arrangements** (e.g. *Camino Real*, *Daft Punk Medley*) automatically merged into clean multi-page PDFs.

---

## Key Features

| Feature | How It Works |
| --- | --- |
| **Auto-Deskew** | Uses computer-vision Hough line transforms to detect music staff angles and straighten crooked scans automatically. |
| **Margin & Binder Cleaning** | Trims away 3-ring binder punch guides, left scanner borders, and horizontal midline dividers. |
| **Dynamic Mark Protection** | Uses an "ink-valley" detection algorithm to strip tiny publisher copyright fine print while strictly preserving low notation, dynamic markings (`ff`, `fff`, `p`), and hairpins. |
| **Performance Cut Highlighting** | Automatically identifies rectangular boxed performance cuts and highlights them in translucent amber (`#FFD54F` at 20% opacity) so band members immediately see cuts. |
| **Spreadsheet-Driven (No Coding)** | Control song order, titles, and page assignments using a simple `.csv` spreadsheet in Microsoft Excel, Apple Numbers, or Google Sheets. |
| **Batch Processing** | Process all instrument parts (Flute, Clarinet, Alto Sax, Trumpet, Trombone, Tuba, etc.) across the entire band in a single run. |

---

## Quick Start (Step-by-Step for Beginners)

You do **not** need programming experience to use this tool. Follow these simple steps:

### Step 1: Install Python

Ensure you have **Python 3.9 or newer** installed on your computer:

- **Mac**: Open the **Terminal** app and check with `python3 --version`. If not installed, download from [python.org](https://www.python.org/downloads/) or run `brew install python`.
- **Windows**: Download the installer from [python.org](https://www.python.org/downloads/). **Important:** During installation, check the box that says **"Add Python to PATH"**.

### Step 2: Clone or Download this Repository

If you use Git:

```bash
git clone https://github.com/sumitake/FlipFolder-Parser.git
cd FlipFolder-Parser
```

Or click the green **Code** button on GitHub and select **Download ZIP**, then unpack the folder.

### Step 3: Install Required Dependencies

Open your command prompt or terminal in the project folder and run:

```bash
pip install -r requirements.txt
```

This installs PyMuPDF, OpenCV, and NumPy for PDF handling and image processing.

### Step 4: Run the Tool on Your Music Packet

Place your scanned instrument PDF (e.g., `Clarinet 1.pdf`) into the folder and run:

```bash
python flip_folder_tool.py "Clarinet 1.pdf"
```

**That's it!** The tool will:

1. Extract every song into the `Extracted_5x7_Charts/` folder.
2. Build a complete flip-folder book named `Clarinet_1_Complete_5x7_FlipFolder.pdf`.

---

## Managing the Repertoire (`arrangements.csv`)

You don't have to touch any Python code to change song names or page orders. Everything is managed in **`arrangements.csv`**, which you can open and edit directly in **Microsoft Excel**, **Apple Numbers**, or **Google Sheets**.

### Manifest Columns

- `title`: The name of the song (e.g., `Johnny_B_Goode`, `Proud_Mary`).
- `page`: The 1-based page number in the scanned PDF document.
- `section`: Either `top` (the upper half-sheet) or `bottom` (the lower half-sheet).

### Example arrangements.csv

```csv
title,page,section
Aint_Nothin_Wrong_With_That,1,top
Johnny_B_Goode,1,bottom
Land_of_1000_Dances,2,top
Seven_Nation_Army,2,bottom
Camino_Real,11,top
Camino_Real,12,top
Proud_Mary,11,bottom
```

### Multi-Page Songs

If an arrangement takes up multiple half-sheets (such as *Camino Real* above, which spans page 11 top and page 12 top), simply **list the title with the same name on consecutive rows**. The tool will automatically detect this and assemble them into a single 2-page PDF chart!

---

## Processing Other Instrument Parts

Marching band packets generally share the exact same song order across the entire band. Once your `arrangements.csv` is set up, you can process any instrument section's packet:

```bash
# Process individual sections:
python flip_folder_tool.py "Trumpet 1.pdf"
python flip_folder_tool.py "Flute.pdf"
python flip_folder_tool.py "Alto Sax 1.pdf"
python flip_folder_tool.py "Mellophone.pdf"
python flip_folder_tool.py "Trombone 1.pdf"
python flip_folder_tool.py "Sousaphone.pdf"

# Or batch-process the entire band at once:
python flip_folder_tool.py "Flute.pdf" "Clarinet 1.pdf" "Alto Sax 1.pdf" "Trumpet 1.pdf" "Trombone 1.pdf"
```

Each run automatically generates:

- Individual 5" × 7" song PDFs in `Extracted_5x7_Charts_<Instrument>/`.
- A compiled master flip folder: `<Instrument>_Complete_5x7_FlipFolder.pdf`.

---

## Starting from Scratch with a New Packet (`--generate-manifest`)

If you have a brand-new packet of music and want to generate a starter spreadsheet template:

```bash
python flip_folder_tool.py "New_Season_Packet.pdf" --generate-manifest
```

The tool will:

1. Inspect every page of the PDF.
2. Automatically detect and filter out blank half-sheets (such as blank packet backsides).
3. Create `New_Season_Packet_arrangements.csv` and `.json` with placeholder song titles.
4. You can open the CSV in Excel, type in your actual song titles, and run!

---

## Advanced Options & CLI Reference

| Flag | Short | Default | Description |
| --- | --- | --- | --- |
| `inputs` | `-i` | *(Required)* | One or more input PDF file paths. |
| `--manifest` | `-m` | `arrangements.csv` | Path to a custom arrangement CSV or JSON file. |
| `--output-dir` | `-o` | `Extracted_5x7_Charts` | Folder where individual 5" × 7" charts are saved. |
| `--master` | | `<Instrument>_Complete_5x7_FlipFolder.pdf` | File path for the compiled master flip-folder book. |
| `--instrument` | | Derived from filename | Explicitly override the instrument name. |
| `--generate-manifest` | | `False` | Scan the PDF, detect blank pages, and generate a starter CSV. |
| `--no-master` | | `False` | Skip generating the combined master flip-folder PDF. |
| `--no-amber` | | `False` | Disable amber highlighting on boxed performance cuts. |
| `--amber-opacity` | | `0.20` (20%) | Set opacity for performance cut highlights (0.0 to 1.0). |
| `--no-deskew` | | `False` | Disable automatic staff line de-skewing. |
| `--dpi` | | `200` | Resolution for image processing and output rendering. |
| `--target-width` | | `504.0` pt (7.0") | Target canvas width in PDF points. |
| `--target-height` | | `360.0` pt (5.0") | Target canvas height in PDF points. |
| `--margin` | | `14.0` pt (~0.2") | Safe edge margin in PDF points. |

---

## Frequently Asked Questions (FAQ)

### Q: How do I import the master PDF into ForScore or MobileSheets?

**A:** The compiled master PDF (`<Instrument>_Complete_5x7_FlipFolder.pdf`) is standard PDF format. AirDrop, email, or copy it via Google Drive / Dropbox to your tablet. In ForScore or MobileSheets, import the PDF directly. Because each chart is standard 5" × 7" landscape, it fills your tablet screen cleanly without wasted black bars.

### Q: Why did the tool skip a page in my PDF?

**A:** Many scanned band packets end with single charts or blank backsides (e.g. only a top chart on the last page). FlipFolder-Parser uses staff density analysis to detect blank half-sheets and automatically omits them so you don't end up with blank charts in your flip folder.

### Q: Does this modify my original scanned PDF?

**A:** No. Your original PDF files are never changed or overwritten. All extracted and standardized charts are saved into separate files.

### Q: Can I turn off the amber cut highlighting?

**A:** Yes. Run with `--no-amber` to output the charts without any color overlays.

---

## Contributing & License

Pull requests and issues are welcome! If you have suggestions for new features, edge-case musical notation formats, or scanner artifacts, feel free to open an issue.

This project is licensed under the **Mozilla Public License 2.0 (MPL 2.0)** - see the [LICENSE](LICENSE) file for details.
