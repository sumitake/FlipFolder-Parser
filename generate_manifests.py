#!/usr/bin/env python3
"""
Full-fidelity Manifest Generator for Alumni Band Music
Extracts half-sheet text via PyMuPDF + Apple Vision OCR,
resolves all songs with zero false positives or flips,
and writes individual JSON manifests for all 19 instruments.
"""

import json
import os
import re
import time

import pymupdf
import Vision
from Cocoa import NSData

SOURCE_DIR = "/Users/josumi/Downloads/Alumni Band Music"
THROWBACK_DIR = os.path.join(SOURCE_DIR, "Throwback Tunes - Please incorporate")
HALFTIME_PATH = os.path.join(SOURCE_DIR, "Halftime", "Rock You Like a Hurricane.pdf")
MANIFEST_DIR = "manifests"

os.makedirs(MANIFEST_DIR, exist_ok=True)

CANONICAL_ORDER = [
    "Aint_Nothin_Wrong_With_That",
    "Johnny_B_Goode",
    "Alive_And_Amplified",
    "Jungle_Boogie",
    "All_Hail_Green_And_Gold",
    "Lets_Groove",
    "Any_Way_You_Want_It",
    "Prince_Of_Thieves",
    "Are_You_Gonna_Be_My_Girl",
    "My_Songs_Know_What_You_Did",
    "Believer",
    "Master_Of_Puppets",
    "Back_In_Black",
    "On_Mustangs",
    "Blister_In_The_Sun",
    "Poker_Face",
    "Born_To_Be_Wild",
    "The_Pretender",
    "Cal_Poly_Fanfare",
    "Pretty_Fly",
    "Camino_Real",
    "Proud_Mary",
    "Ride_High_You_Mustangs",
    "Centerfold",
    "Rock_Lobster",
    "Confident",
    "Runaway_Baby",
    "Crazy_Train",
    "Sell_Out",
    "Daft_Punk_Medley",
    "Send_Out_A_Cheer",
    "Shake",
    "Dirty_Deeds_Done_Dirt_Cheap",
    "Sir_Duke",
    "Come_On_Feel_The_Noize",
    "Stadium_Jams_Vol_5",
    "Fireball",
    "Forget_You",
    "Think",
    "Freeze_Frame",
    "Thnks_fr_th_Mmrs",
    "Get_It_On",
    "The_Time_Warp",
    "Happy_Together",
    "Touch_Me",
    "Happy",
    "Vehicle",
    "Hey_Baby",
    "Walking_On_Sunshine",
    "Hey_Pachuco",
    "Word_Up",
    "Yea_Poly",
    "Holiday",
    "You_Can_Call_Me_Al",
    "I_Dont_Care",
    "You_Dropped_A_Bomb_On_Me",
    "I_Saw_Her_Standing_There",
    "In_The_Stone",
    "The_Impression_That_I_Get",
]

PATTERNS = [
    ("Aint_Nothin_Wrong_With_That", [r"ain['\u2019]?t nothin", r"nothin['\u2019]? wrong", r"andrew ramsey", r"shannon sanders", r"fast soul"]),
    ("Johnny_B_Goode", [r"johnny b\.? goode", r"\bb\.? goode\b", r"chuck berry"]),
    ("Alive_And_Amplified", [r"alive and amplified", r"alive & amplified", r"mooney suzuki"]),
    ("Jungle_Boogie", [r"jungle boog", r"kool & the gang", r"kool and the gang", r"ronald bell"]),
    ("All_Hail_Green_And_Gold", [r"all hail green", r"green and gold", r"alma mater"]),
    ("Lets_Groove", [r"let['\u2019]?s groove", r"dance groove"]),
    ("Any_Way_You_Want_It", [r"any way you want", r"fast rock.*152"]),
    ("Prince_Of_Thieves", [r"prince of thieves", r"robin hood", r"michael kamen", r"m-?9[17]5", r"mysteriously", r"s16 w"]),
    ("Are_You_Gonna_Be_My_Girl", [r"gonna be my girl", r"are you gonna", r"\bjet\b", r"be my gir"]),
    ("My_Songs_Know_What_You_Did", [r"songs know what you did", r"light ['\u2019]?em up", r"save rock and roll"]),
    ("Believer", [r"\bbeliever\b", r"imagine dragons"]),
    ("Master_Of_Puppets", [r"master of puppets", r"metallica"]),
    ("Back_In_Black", [r"back in black", r"heavy rock feel.*108"]),
    ("On_Mustangs", [r"on mustangs", r"on, mustangs", r"davidson.*1908-1976"]),
    ("Blister_In_The_Sun", [r"blister in the sun", r"violent femmes", r"gano", r"fast rock.*208"]),
    ("Poker_Face", [r"poker face", r"lady gaga", r"germanotta", r"electropop dance feel"]),
    ("Born_To_Be_Wild", [r"born to be wild", r"steppenwolf", r"mars bonfire", r"rock.*156"]),
    ("The_Pretender", [r"the pretender", r"\bpretender\b", r"foo fighters", r"grohl", r"fast rock.*172"]),
    ("Cal_Poly_Fanfare", [r"cal poly fan[tf]are", r"stadium salute", r"poly fan[tf]are", r"higgins/woodruff", r"woodruff"]),
    ("Pretty_Fly", [r"pretty fly", r"white guy", r"offspring", r"fast thrash feel"]),
    ("Camino_Real", [r"camino real", r"m-?957\b", r"\b957\b", r"56-w", r"lb-w", r"ls6-w", r"l5b-w"]),
    ("Proud_Mary", [r"proud mary", r"creedence", r"fogerty", r"\bccr\b"]),
    ("Ride_High_You_Mustangs", [r"ride high", r"you mustangs", r"lon[gq]:", r"as w[orite]{2,4}n"]),
    ("Centerfold", [r"\bcenterfold\b", r"heavy rock.*106"]),
    ("Rock_Lobster", [r"rock lobster", r"b-?52", r"driving rock.*9-end"]),
    ("Confident", [r"\bconfident\b", r"demi lovato", r"rock shuffle.*144"]),
    ("Runaway_Baby", [r"runaway baby", r"fast rock.*170"]),
    ("Crazy_Train", [r"crazy train", r"crazy.*rain", r"ozzy", r"osbourne", r"randy rhoads", r"bob daisley", r"m-?1071"]),
    ("Sell_Out", [r"sell ?out", r"reel big fish", r"m-?977", r"short:? 9-end \(coda\)", r"driving rock.*9-end", r"9-end.*coda"]),
    ("Daft_Punk_Medley", [r"daft punk", r"baft pynk", r"harder, better", r"technologic", r"medley.*clarinet 2"]),
    ("Send_Out_A_Cheer", [r"send out a cheer", r"out a cheer", r"quick march"]),
    ("Shake", [r"otis redding.*shake", r"shake.*otis", r"\bshake\b", r"doubletime disco"]),
    ("Dirty_Deeds_Done_Dirt_Cheap", [r"dirty deeds", r"oirty deeds"]),
    ("Sir_Duke", [r"sir duke", r"stevie wonder"]),
    ("Come_On_Feel_The_Noize", [r"feel the noize", r"come on feel", r"cum on feel", r"cume on feel", r"quiet riot"]),
    ("Stadium_Jams_Vol_5", [r"stadium jams", r"dies irae", r"bald mountain", r"gustav holst", r"holst", r"feroce.*tuba"]),
    ("Fireball", [r"\bfireball\b", r"pitbull", r"salsa.*12"]),
    ("Forget_You", [r"forget you", r"cee ?lo", r"motown feel.*132"]),
    ("Think", [r"\bthi+nk\b", r"aretha", r"ted white"]),
    ("Freeze_Frame", [r"freeze[- ]frame"]),
    ("Thnks_fr_th_Mmrs", [r"thnks", r"mmrs", r"thanks for the mem", r"patrick stump", r"alternative rock.*164"]),
    ("Get_It_On", [r"get it on", r"gei 11 on", r"11 on", r"bill chase", r"allegro moderato.*134", r"alegro moderato"]),
    ("The_Time_Warp", [r"time warp", r"rocky horror"]),
    ("Happy_Together", [r"happy together", r"turtles", r"swingfeel.*148"]),
    ("Touch_Me", [r"touch me", r"the doors", r"krieger"]),
    ("Happy", [r"funky and hip", r"pharrell.*happy", r"happy.*pharrell", r"\bhappy\b"]),
    ("Vehicle", [r"\bvehicle\b", r"[sS]hicle", r"ides of march", r"peterik", r"m-?852", r"\b852\b"]),
    ("Hey_Baby", [r"hey!? baby!?", r"bruce channel", r"margaret cobb", r"moderate rock.*12", r"m-?949"]),
    ("Walking_On_Sunshine", [r"walking on sunshine", r"katrina"]),
    ("Hey_Pachuco", [r"hey pachuco", r"pachuco", r"uptempo swing.*272", r"m-?999", r"m-?998"]),
    ("Word_Up", [r"wor[-do0b] [uU]p", r"cameo", r"m-?1041"]),
    ("Yea_Poly", [r"yea poly", r"yea, poly", r"yca poly", r"yca paly", r"yea polt", r"yea foly", r"warren ba[ck]", r"may 19", r"i[al]tod v[eia]"]),
    ("Holiday", [r"\bholiday\b", r"green day", r"heavy head banging"]),
    ("You_Can_Call_Me_Al", [r"call ?me al", r"paul simon"]),
    ("I_Dont_Care", [r"i don['\u2019]?t care", r"idont care", r"icona pop", r"norman greenbaum", r"joseph trohman", r"heavy rock shuf.*14", r"38-48"]),
    ("You_Dropped_A_Bomb_On_Me", [r"dropped a bomb", r"bomb on me", r"gap band", r"nuclear funk.*148"]),
    ("I_Saw_Her_Standing_There", [r"saw her standing there", r"standing there", r"fast rock.*178"]),
    ("In_The_Stone", [r"in the stone"]),
    ("The_Impression_That_I_Get", [r"impression that i get", r"impression that get", r"bosstones"]),
]

HALFTIME_MAPPING = {
    "Flute 1": 1, "Flute 2": 1, "Clarinet 1": 2, "Clarinet 2": 2,
    "Alto 1": 3, "Alto 2": 3, "Tenor Sax": 4, "Trumpet 1": 5,
    "Trumpet 2": 6, "Trumpet 3": 7, "French Horn": 8, "Trombone 1": 9,
    "Trombone 2": 10, "Baritone": 11, "Tuba": 12, "Snare": 13,
    "Cymbals": 14, "Tenor Drums": 15, "Bass Drum": 16,
}

THROWBACK_MAP = {
    "Flute 1": "1) Flute 1 Throwbacks.pdf",
    "Flute 2": "2) Flute 2 - Throwbacks.pdf",
    "Clarinet 1": "3) Clarinet 1 - Throwbacks.pdf",
    "Clarinet 2": "4) Clarinet 2 - Throwbacks.pdf",
    "Alto 1": "5) Alto 1 - Throwbacks.pdf",
    "Alto 2": "6) Alto 2 - Throwbacks.pdf",
    "Tenor Sax": "7) Tenor - Throwbacks.pdf",
    "Trumpet 1": "8) Trumpet 1 - Throwbacks.pdf",
    "Trumpet 2": "9) Trumpet 2 - Throwbacks.pdf",
    "Trumpet 3": "10) Trumpet 3 - Throwbacks.pdf",
    "Trombone 1": "11) Trombone 1 - Throwbacks.pdf",
    "Trombone 2": "12) Trombone 2 - Throwbacks.pdf",
    "Baritone": "13) Baritone - Throwbacks.pdf",
    "French Horn": "14) French Horn - Throwbacks.pdf",
    "Tuba": "15) Tuba - Throwbacks.pdf",
    "Snare": "16) Snare - Throwbacks.pdf",
    "Tenor Drums": "17) Tenor Drums - Throwbacks.pdf",
    "Bass Drum": "18) Bass Drum - Throwbacks.pdf",
    "Cymbals": "19) Cymbals - Throwbacks.pdf",
}

def ocr_pdf_pages(pdf_path):
    doc = pymupdf.open(pdf_path)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(False)
    
    pages_data = []
    for p_idx in range(len(doc)):
        page = doc[p_idx]
        pix = page.get_pixmap(dpi=150)
        png_data = pix.tobytes("png")
        nsdata = NSData.dataWithBytes_length_(png_data, len(png_data))
        handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(nsdata, None)
        handler.performRequests_error_([req], None)
        
        top_list = []
        bot_list = []
        for obs in req.results():
            y_mid = obs.boundingBox().origin.y + obs.boundingBox().size.height * 0.5
            txt = obs.topCandidates_(1)[0].string()
            if y_mid >= 0.48:
                top_list.append(txt)
            if y_mid <= 0.52:
                bot_list.append(txt)
                
        pages_data.append((top_list, bot_list))
    doc.close()
    return pages_data

def build_manifest_for_instrument(inst_name):
    pdf_path = os.path.join(SOURCE_DIR, f"{inst_name}.pdf")
    t0 = time.time()
    print(f"[{inst_name}] Scanning booklet pages...")
    pages_data = ocr_pdf_pages(pdf_path)
    
    detected = [] # (page_1based, section, title)
    for p_idx, (top_list, bot_list) in enumerate(pages_data):
        p_num = p_idx + 1
        for sec, text_list in [("top", top_list), ("bottom", bot_list)]:
            text_full = " ".join(text_list).lower()
            if len(text_list) <= 1 and not any(k in text_full for k in ["fanfare", "long:", "short:"]):
                continue
            if any(w in text_full for w in ["intended to be blank", "this page was intended", "this page is intended"]):
                continue
                
            matched = None
            for title, pats in PATTERNS:
                if any(re.search(p, text_full) for p in pats):
                    matched = title
                    break
            if matched:
                detected.append((p_num, sec, matched))

    by_title = {}
    for p, sec, t in detected:
        if t not in by_title:
            by_title[t] = []
        by_title[t].append({"page": p, "section": sec})
        
    catalog = []
    # 1. Main booklet
    for t in CANONICAL_ORDER:
        if t in by_title:
            catalog.append({"title": t, "pages": by_title[t]})

    # 2. Throwbacks
    tb_file = THROWBACK_MAP[inst_name]
    tb_full = os.path.join(THROWBACK_DIR, tb_file)
    if inst_name == "Cymbals":
        catalog.append({"title": "Dancing_Queen", "file": tb_full, "pages": [{"page": 1, "section": "full"}]})
        catalog.append({"title": "Karn_Evil_9", "file": tb_full, "pages": [{"page": 2, "section": "full"}]})
        catalog.append({"title": "Magic_Carpet_Ride", "file": tb_full, "pages": [{"page": 3, "section": "full"}]})
        catalog.append({"title": "The_Lion_Sleeps_Tonight", "file": tb_full, "pages": [{"page": 5, "section": "full"}]})
        catalog.append({"title": "Radar_Love", "file": tb_full, "pages": [{"page": 4, "section": "full"}]})
    else:
        catalog.append({"title": "Dancing_Queen", "file": tb_full, "pages": [{"page": 1, "section": "full"}]})
        catalog.append({"title": "Karn_Evil_9", "file": tb_full, "pages": [{"page": 2, "section": "full"}, {"page": 3, "section": "full"}]})
        catalog.append({"title": "Magic_Carpet_Ride", "file": tb_full, "pages": [{"page": 4, "section": "full"}]})
        catalog.append({"title": "The_Lion_Sleeps_Tonight", "file": tb_full, "pages": [{"page": 5, "section": "full"}]})
        catalog.append({"title": "Radar_Love", "file": tb_full, "pages": [{"page": 6, "section": "full"}]})

    # 3. Halftime
    ht_page = HALFTIME_MAPPING[inst_name]
    catalog.append({
        "title": "Rock_You_Like_A_Hurricane",
        "file": HALFTIME_PATH,
        "pages": [{"page": ht_page, "section": "clean_top"}]
    })

    out_json = os.path.join(MANIFEST_DIR, f"{inst_name}_arrangements.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)

    elapsed = time.time() - t0
    print(f"[{inst_name}] Generated manifest with {len(catalog)} pieces in {elapsed:.1f}s -> {out_json}")
    return catalog

if __name__ == "__main__":
    t_start = time.time()
    for inst in sorted(HALFTIME_MAPPING.keys()):
        build_manifest_for_instrument(inst)
    print(f"All 19 manifests generated in {time.time() - t_start:.1f}s.")
