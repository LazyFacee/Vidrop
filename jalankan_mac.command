#!/bin/bash
# Jalankan Vidrop dari kode sumber di macOS (butuh Python 3.10+ dengan Tk).
cd "$(dirname "$0")"
python3 -m pip install -q -U -r requirements.txt
python3 vidrop.py
