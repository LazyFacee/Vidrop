# -*- coding: utf-8 -*-
"""Vidrop - dua bahasa (Indonesia / English)."""
import os
import sys

_STR = {
    "id": {
        # navigasi & judul
        "nav_download": "Unduh", "nav_convert": "Konversi", "nav_folder": "Folder",
        "title_download": "UNDUH", "title_convert": "KONVERSI",
        "paste_link": "Tempel link", "choose_file": "Pilih file",
        # riwayat
        "recent": "Aktivitas terbaru", "recent_empty": "Belum ada aktivitas",
        "recent_empty_sub": "Unduhan dan konversi kamu muncul di sini.",
        "open_folder": "Buka folder", "clear_history_q": "Hapus semua riwayat aktivitas?",
        "ago_now": "baru saja", "ago_min": "{n} menit lalu", "ago_hour": "{n} jam lalu", "ago_day": "{n} hari lalu",
        "h_video": "Video", "h_audio": "Audio", "h_thumb": "Thumbnail", "h_conv": "Konversi",
        # kartu link
        "link_placeholder": "Tempel link video di sini", "other_sites": "+1000 situs",
        # preview
        "no_video": "Belum ada video", "preview_hint": "Tempel link di atas untuk melihat preview.",
        "no_title": "Tanpa judul", "up_to": "tersedia hingga {res}",
        # mode & kualitas
        "seg_video": "Video", "seg_audio": "Musik", "seg_thumb": "Thumbnail",
        "q_max": "Maks · {res}", "q_best": "Maksimal tersedia", "lossless": "Lossless · kualitas asli",
        "aq_best": "Terbaik · 320k", "aq_mid": "Sedang · 192k", "aq_low": "Hemat · 128k",
        "thumb_best": "Resolusi tertinggi",
        "save_in": "Simpan di", "change": "Ganti",
        # tombol aksi
        "dl_video": "Unduh · {fmt}", "dl_audio": "Unduh · {fmt}", "dl_thumb": "Unduh · {fmt}",
        "cancel": "Batal", "cancelling": "Membatalkan...", "processing": "Memproses...",
        "convert": "Konversi", "extract_audio": "Ambil audio",
        # status unduh
        "st_ready": "Siap. Tempel link untuk mulai.", "st_fetch": "Mengambil info video...",
        "st_empty_link": "Link masih kosong. Tempel dulu link videonya.",
        "st_valid": "Link valid. Pilih format lalu tekan Unduh.", "st_start": "Memulai...",
        "st_downloading": "Mengunduh {kind} · {pct}%", "kind_video": "video", "kind_audio": "audio", "kind_file": "file",
        "st_eta": "sisa {t}", "st_done": "Selesai · {name}", "st_dl_cancelled": "Unduhan dibatalkan. File sementara dibersihkan.",
        "st_cancelling_dl": "Membatalkan unduhan...", "st_proc_file": "Memproses file...", "st_thumb": "Mengunduh thumbnail...",
        "st_try_mkv": "Format tidak cocok, mencoba MKV...",
        "st_wait_engine": "Menunggu komponen YouTube siap...",
        "st_engine_prep": "Menyiapkan komponen YouTube (sekali saja, ±40 MB)...",
        "st_engine_prep_pct": "Menyiapkan komponen YouTube (sekali saja)... {pct}%",
        "st_engine_fail": "Komponen YouTube gagal disiapkan. Cek internet lalu buka ulang.",
        "st_blocked": "Instagram butuh login, jadi tidak didukung. Coba YouTube, TikTok, atau X.",
        "busy": "Selesaikan atau batalkan proses yang berjalan dulu.",
        # error
        "err_unsupported": "Link ini belum didukung. Pastikan link langsung ke video.",
        "err_login": "Konten ini butuh login, dan Vidrop tidak mendukung konten yang memerlukan login.",
        "err_bot": "YouTube meminta verifikasi untuk video ini. Coba lagi nanti atau coba video lain.",
        "err_format": "Resolusi itu tidak tersedia. Coba pilih resolusi lain.",
        "err_network": "Koneksi internet bermasalah. Periksa jaringan lalu coba lagi.",
        "err_429": "Terlalu banyak permintaan. Tunggu beberapa menit lalu coba lagi.",
        "err_ffmpeg": "Gagal memproses file. Coba format lain di Opsi.",
        "err_prefix": "Gagal: {msg}",
        # konversi
        "cv_no_file": "Belum ada file dipilih", "cv_no_files_title": "Belum ada file",
        "cv_pick_hint": "Klik Pilih file untuk memulai.", "cv_n_files": "{n} file dipilih",
        "cv_total": "total {size}", "cv_ready": "Siap dikonversi. Pilih format hasil lalu tekan Konversi.",
        "cv_skipped": "({n} file beda jenis dilewati)", "cv_pick_status": "Pilih file untuk dikonversi.",
        "cv_unsupported": "Jenis file itu belum didukung.", "cv_no_ffmpeg": "ffmpeg tidak ditemukan, konversi video/audio tidak tersedia.",
        "cv_converting": "Mengonversi {text}", "cv_done": "Selesai · {n} file tersimpan", "cv_some_failed": "{n} gagal: {name}",
        "cv_cancelled": "Konversi dibatalkan.", "cv_cancelling": "Membatalkan konversi...", "cv_none": "tidak ada hasil",
        "cap_format": "Format hasil", "cap_quality": "Kualitas", "cap_size": "Ukuran", "cap_channels": "Kanal",
        "cap_smooth": "Kelancaran", "cap_gif_size": "Ukuran (tinggi)",
        "cat_video": "Video", "cat_audio": "Audio", "cat_image": "Gambar",
        "cq_high": "Tinggi", "cq_mid": "Seimbang", "cq_low": "Hemat ruang", "sz_orig": "Ukuran asli",
        "ch_orig": "Asli", "ch_stereo": "Stereo", "ch_mono": "Mono",
        "gif_1": "Tajam · 15 fps", "gif_2": "Sedang · 12 fps", "gif_3": "Ringan · 8 fps",
        "iw_3840": "Maks. 3840 px", "iw_1920": "Maks. 1920 px", "iw_1280": "Maks. 1280 px", "iw_800": "Maks. 800 px",
        "audio_only": " · audio saja", "pick_dialog": "Pilih file untuk dikonversi",
        "ft_all": "Semua media", "ft_video": "Video", "ft_audio": "Audio", "ft_image": "Gambar",
        # grafik
        "speed": "Kecepatan", "speed_idle": "Grafik kecepatan muncul saat mengunduh",
        # opsi
        "opt_title": "Opsi", "opt_sub": "Bahasa dan format hasil unduhan.", "language": "Bahasa",
        "lang_auto": "Otomatis", "f_video": "Format video", "f_audio": "Format musik", "f_thumb": "Format thumbnail",
        "no_login_note": "Vidrop hanya mendukung konten yang bisa dibuka tanpa login. Instagram dan konten privat tidak didukung.",
        "done": "Selesai", "busy_close": "Proses masih berjalan. Tutup dan batalkan?",
        "legal": "Unduh hanya konten milikmu atau yang memang boleh diunduh. Hormati hak cipta dan ketentuan platform.",
    },
    "en": {
        "nav_download": "Download", "nav_convert": "Convert", "nav_folder": "Folder",
        "title_download": "DOWNLOAD", "title_convert": "CONVERT",
        "paste_link": "Paste link", "choose_file": "Choose file",
        "recent": "Recent activity", "recent_empty": "Nothing here yet",
        "recent_empty_sub": "Your downloads and conversions show up here.",
        "open_folder": "Open folder", "clear_history_q": "Clear all recent activity?",
        "ago_now": "just now", "ago_min": "{n} min ago", "ago_hour": "{n} h ago", "ago_day": "{n} d ago",
        "h_video": "Video", "h_audio": "Audio", "h_thumb": "Thumbnail", "h_conv": "Convert",
        "link_placeholder": "Paste a video link here", "other_sites": "+1000 sites",
        "no_video": "No video yet", "preview_hint": "Paste a link above to see a preview.",
        "no_title": "Untitled", "up_to": "up to {res} available",
        "seg_video": "Video", "seg_audio": "Audio", "seg_thumb": "Thumbnail",
        "q_max": "Max · {res}", "q_best": "Best available", "lossless": "Lossless · original quality",
        "aq_best": "Best · 320k", "aq_mid": "Medium · 192k", "aq_low": "Small · 128k",
        "thumb_best": "Highest resolution",
        "save_in": "Save to", "change": "Change",
        "dl_video": "Download · {fmt}", "dl_audio": "Download · {fmt}", "dl_thumb": "Download · {fmt}",
        "cancel": "Cancel", "cancelling": "Cancelling...", "processing": "Processing...",
        "convert": "Convert", "extract_audio": "Extract audio",
        "st_ready": "Ready. Paste a link to start.", "st_fetch": "Fetching video info...",
        "st_empty_link": "The link is empty. Paste a video link first.",
        "st_valid": "Link looks good. Pick a format, then press Download.", "st_start": "Starting...",
        "st_downloading": "Downloading {kind} · {pct}%", "kind_video": "video", "kind_audio": "audio", "kind_file": "file",
        "st_eta": "{t} left", "st_done": "Done · {name}", "st_dl_cancelled": "Download cancelled. Temporary files were cleaned up.",
        "st_cancelling_dl": "Cancelling download...", "st_proc_file": "Processing file...", "st_thumb": "Downloading thumbnail...",
        "st_try_mkv": "Format didn't fit, trying MKV...",
        "st_wait_engine": "Waiting for the YouTube component...",
        "st_engine_prep": "Setting up the YouTube component (one time, ~40 MB)...",
        "st_engine_prep_pct": "Setting up the YouTube component (one time)... {pct}%",
        "st_engine_fail": "YouTube component setup failed. Check your internet and reopen.",
        "st_blocked": "Instagram requires login, so it isn't supported. Try YouTube, TikTok, or X.",
        "busy": "Finish or cancel the running task first.",
        "err_unsupported": "This link isn't supported yet. Make sure it points directly to a video.",
        "err_login": "This content requires login, and Vidrop doesn't support content that needs login.",
        "err_bot": "YouTube is asking for verification on this video. Try again later or try another video.",
        "err_format": "That resolution isn't available. Try another one.",
        "err_network": "Internet connection problem. Check your network and try again.",
        "err_429": "Too many requests. Wait a few minutes and try again.",
        "err_ffmpeg": "Couldn't process the file. Try another format in Settings.",
        "err_prefix": "Failed: {msg}",
        "cv_no_file": "No file selected", "cv_no_files_title": "No files yet",
        "cv_pick_hint": "Click Choose file to begin.", "cv_n_files": "{n} files selected",
        "cv_total": "total {size}", "cv_ready": "Ready. Pick an output format, then press Convert.",
        "cv_skipped": "({n} files of a different type were skipped)", "cv_pick_status": "Choose files to convert.",
        "cv_unsupported": "That file type isn't supported yet.", "cv_no_ffmpeg": "ffmpeg not found, video/audio conversion is unavailable.",
        "cv_converting": "Converting {text}", "cv_done": "Done · {n} files saved", "cv_some_failed": "{n} failed: {name}",
        "cv_cancelled": "Conversion cancelled.", "cv_cancelling": "Cancelling conversion...", "cv_none": "no output",
        "cap_format": "Output format", "cap_quality": "Quality", "cap_size": "Size", "cap_channels": "Channels",
        "cap_smooth": "Smoothness", "cap_gif_size": "Size (height)",
        "cat_video": "Video", "cat_audio": "Audio", "cat_image": "Image",
        "cq_high": "High", "cq_mid": "Balanced", "cq_low": "Small size", "sz_orig": "Original size",
        "ch_orig": "Original", "ch_stereo": "Stereo", "ch_mono": "Mono",
        "gif_1": "Sharp · 15 fps", "gif_2": "Medium · 12 fps", "gif_3": "Light · 8 fps",
        "iw_3840": "Max 3840 px", "iw_1920": "Max 1920 px", "iw_1280": "Max 1280 px", "iw_800": "Max 800 px",
        "audio_only": " · audio only", "pick_dialog": "Choose files to convert",
        "ft_all": "All media", "ft_video": "Video", "ft_audio": "Audio", "ft_image": "Images",
        "speed": "Speed", "speed_idle": "The speed graph appears while downloading",
        "opt_title": "Settings", "opt_sub": "Language and download formats.", "language": "Language",
        "lang_auto": "Auto", "f_video": "Video format", "f_audio": "Audio format", "f_thumb": "Thumbnail format",
        "no_login_note": "Vidrop only supports content that can be opened without logging in. Instagram and private content are not supported.",
        "done": "Done", "busy_close": "A task is still running. Close and cancel it?",
        "legal": "Only download content you own or are allowed to download. Respect copyright and platform terms.",
    },
}

LANG_NAMES = {"id": "Bahasa Indonesia", "en": "English"}
_lang = "en"


def set_lang(code):
    global _lang
    _lang = code if code in _STR else "en"


def get_lang():
    return _lang


def tr(key, **kw):
    s = _STR.get(_lang, {}).get(key) or _STR["en"].get(key) or key
    return s.format(**kw) if kw else s


def detect_lang():
    """Bahasa sistem: Indonesia -> 'id', selain itu 'en'."""
    try:
        if sys.platform.startswith("win"):
            import ctypes
            lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "id" if (lid & 0x3FF) == 0x21 else "en"
        import locale
        loc = (os.environ.get("LC_ALL") or os.environ.get("LANG") or (locale.getlocale()[0] or "")).lower()
        if loc.startswith("id") or "indonesia" in loc:
            return "id"
        if sys.platform == "darwin":
            import subprocess
            out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True,
                                 timeout=2).stdout.lower()
            first = out.replace("(", "").replace(")", "").replace('"', "").split(",")[0].strip()
            return "id" if first.startswith("id") else "en"
    except Exception:
        pass
    return "en"
