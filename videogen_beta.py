# ==========================================================
# ✅ VIDEO GENERATOR FINAL V7
# Animasi sapuan blok penuh kiri→kanan (judul, subjudul, isi)
# Highlight ikut tersapu bersamaan (bukan per huruf/kata)
# ==========================================================
from moviepy.editor import ImageClip, CompositeVideoClip, concatenate_videoclips, VideoClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import os, re, sys

# ---------- KONFIG ----------
VIDEO_SIZE = (720, 1280)   # (W, H)
BG_COLOR = (0, 0, 0)
TEXT_COLOR = (255, 255, 255, 255)
HIGHLIGHT_COLOR = (0, 124, 188, 255)
FPS = 60
OVERLAY_FILE = "semangat.png"

FONTS = {
    "upper": "ProximaNova-Bold.ttf",
    "judul": "DMSerifDisplay-Regular.ttf",
    "subjudul": "ProximaNova-Regular.ttf",
    "isi": "Poppins-Bold.ttf",
}

# ---------- UTIL ----------
def load_font_safe(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        print(f"⚠️ Font gagal dimuat: {path} → fallback default")
        return ImageFont.load_default()

def ease_sweep(t: float):
    # Easing halus mirip “mask reveal” (lambat-awal/akhir, cepat-tengah)
    t = max(0.0, min(1.0, t))
    return 1 - pow(1 - pow(t, 1.5), 3)

# ==========================================================
# TEXT PROCESSOR
# ==========================================================
class StableTextProcessor:
    def __init__(self, font, max_width, margin_x=70):
        self.font = font
        self.max_width = max_width
        self.margin_x = margin_x
        self.margin_right = 90
        self.line_height = self._get_line_height()

    def _get_line_height(self):
        try:
            bbox = self.font.getbbox("Hgypq")
            return max(bbox[3] - bbox[1] + 10, 34)
        except Exception:
            return 42

    def _get_text_width(self, text):
        try:
            return self.font.getlength(text)
        except Exception:
            # fallback kira-kira
            return len(text) * 15

    def parse_text_with_highlights(self, text):
        # Pisah blok [[...]] (ber-highlight) dengan teks biasa
        parts = re.split(r'(\[\[.*?\]\])', text)
        segs = []
        for p in parts:
            if p.startswith('[[') and p.endswith(']]'):
                segs.append({'text': p[2:-2].replace('|', ' '), 'is_highlight': True})
            elif p.strip():
                segs.append({'text': p.replace('|', ' '), 'is_highlight': False})
        return segs or [{'text': text, 'is_highlight': False}]

    def smart_wrap_with_highlights(self, text):
        segs = self.parse_text_with_highlights(text)
        words = []
        for s in segs:
            for w in s['text'].split():
                words.append({'word': w, 'is_highlight': s['is_highlight']})

        lines, cur, cur_w = [], [], 0
        avail = self.max_width - self.margin_x - self.margin_right
        for wi in words:
            wlen = self._get_text_width(wi['word'] + " ")
            if cur_w + wlen <= avail:
                cur.append(wi); cur_w += wlen
            else:
                lines.append(cur); cur, cur_w = [wi], wlen
        if cur:
            lines.append(cur)
        return lines

    # ------------------------------------------------------
    # RENDER: sapuan blok penuh (mask horizontal per baris)
    # ------------------------------------------------------
    def render_lines_wipe(self, lines, base_y, progress):
        # progress: 0..1
        base = Image.new("RGBA", VIDEO_SIZE, BG_COLOR + (255,))
        hl_layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
        txt_layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
        hld = ImageDraw.Draw(hl_layer)
        td = ImageDraw.Draw(txt_layer)

        y = base_y
        # Hitung lebar maksimum baris (untuk sapuan terasa konsisten)
        total_w_per_line = []
        for line in lines:
            line_w = sum(self._get_text_width(w['word'] + " ") for w in line)
            total_w_per_line.append(int(line_w))

        # Sapuan tiap baris: pakai easing, lalu diaplikasikan ke lebar baris
        for idx, line in enumerate(lines):
            line_total_w = total_w_per_line[idx]
            sweep = int(line_total_w * ease_sweep(progress))

            # Layer per-baris agar mudah di-mask
            line_txt = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
            ltd = ImageDraw.Draw(line_txt)
            x_cursor = self.margin_x

            # 1) Gambar highlight di bawah kata yang is_highlight, TAPI clamp sampai sweep
            #    — highlight dan teks akan muncul bersama (bukan per huruf)
            #    — rectangle dibatasi oleh sweep untuk hasil "tirai dibuka"
            x = self.margin_x
            for w in line:
                w_width = int(self._get_text_width(w['word'] + " "))
                seg_left = x
                seg_right = x + w_width
                sweep_right = self.margin_x + sweep

                if w['is_highlight']:
                    # batas highlight = bagian yang sudah tersapu
                    hl_left = max(seg_left - 4, self.margin_x - 4)
                    hl_right = min(seg_right, sweep_right)
                    if hl_right > hl_left:
                        # subpixel-ish: 3 layer tipis untuk soft edge (anti patah)
                        for i in range(3):
                            offset = i * 0.4
                            alpha = int(255 * (1 - 0.35 * i))
                            hld.rectangle([hl_left + offset,
                                           y + 4,
                                           hl_right + offset,
                                           y + self.line_height + 4],
                                          fill=(HIGHLIGHT_COLOR[0], HIGHLIGHT_COLOR[1],
                                                HIGHLIGHT_COLOR[2], alpha))
                x = seg_right

            # 2) Gambar teks penuh pada layer baris, lalu MASK-kan dengan sapuan (rect mask)
            x = self.margin_x
            for w in line:
                ltd.text((x, y), w['word'] + " ", font=self.font, fill=TEXT_COLOR)
                x += int(self._get_text_width(w['word'] + " "))

            # Buat mask rectangle untuk sapuan baris ini
            # Hanya area sampai sweep yang terlihat
            if sweep > 0:
                mask = Image.new("L", VIDEO_SIZE, 0)
                mdraw = ImageDraw.Draw(mask)
                mdraw.rectangle([self.margin_x - 2, y - 2,
                                 self.margin_x + sweep + 2, y + self.line_height + 10], fill=255)
                # Tempel line_txt ke txt_layer sesuai mask
                txt_layer = Image.composite(line_txt, txt_layer, mask)

            y += self.line_height

        # Komposit akhir
        frame = Image.alpha_composite(Image.alpha_composite(base, hl_layer), txt_layer).convert("RGB")
        return np.array(frame)

# ==========================================================
# LAYOUT + VIDEO GENERATORS
# ==========================================================
def calculate_adaptive_layout(text, font_path, size, margin_x, base_y_ratio=0.60):
    font = load_font_safe(font_path, size)
    proc = StableTextProcessor(font, VIDEO_SIZE[0], margin_x)
    lines = proc.smart_wrap_with_highlights(text)
    base_y = int(VIDEO_SIZE[1] * base_y_ratio)
    total_h = len(lines) * proc.line_height
    # Hindari jatuh melewati bawah
    batas_bawah = VIDEO_SIZE[1] - 160
    if base_y + total_h > batas_bawah:
        base_y = max(80, base_y - (base_y + total_h - batas_bawah))
    return {'lines': lines, 'processor': proc, 'base_y': base_y}

def render_block_wipe(text, font_path, size, dur, base_y_ratio):
    layout = calculate_adaptive_layout(text, font_path, size, margin_x=70, base_y_ratio=base_y_ratio)
    proc, lines, base_y = layout['processor'], layout['lines'], layout['base_y']

    def make_frame(t):
        p = ease_sweep(min(1.0, t / dur))
        return proc.render_lines_wipe(lines, base_y, p)

    return VideoClip(make_frame, duration=dur).set_fps(FPS)

# ==========================================================
# PARSER MULTI-BARIS (Judul/Subjudul/Isi)
# ==========================================================
def baca_semua_berita_stable(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()

        data, current, key, isi_count, buf = [], {}, None, 1, []

        def commit():
            nonlocal buf, key, current
            if key is not None and buf:
                joined = " ".join(buf).strip()
                if joined:
                    current[key] = (current.get(key, "") + " " + joined).strip()
            buf = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("Judul:"):
                commit()
                if current:
                    data.append(current)
                    current, isi_count = {}, 1
                key = "Judul"
                content = line.replace("Judul:", "").strip()
                buf = [content] if content else []
                continue

            if line.startswith("Subjudul:"):
                commit()
                key = "Subjudul"
                content = line.replace("Subjudul:", "").strip()
                buf = [content] if content else []
                continue

            if line.startswith("Isi:"):
                commit()
                key = f"Isi_{isi_count}"; isi_count += 1
                content = line.replace("Isi:", "").strip()
                buf = [content] if content else []
                continue

            # lanjutan baris sebelumnya (judul/subjudul/isi)
            buf.append(line)

        commit()
        if current:
            data.append(current)
        return data
    except Exception as e:
        print("parse fail:", e)
        return []

# ==========================================================
# DURASI
# ==========================================================
def hitung_durasi_isi(text):
    clean = re.sub(r'\[\[.*?\]\]', lambda m: m.group(0)[2:-2], text)
    w = len(clean.split())
    # lebih santai agar sapuan terasa halus
    return round(max(3.0, min(12.0, w / 18.0)), 2)

# ==========================================================
# BUILD VIDEO
# ==========================================================
def buat_video_stable(data):
    clips = []

    judul = data.get('Judul', '').strip()
    subjudul = data.get('Subjudul', '').strip()

    if judul:
        clips.append(render_block_wipe(judul, FONTS['judul'], 54, dur=3.0, base_y_ratio=0.35))
    if subjudul:
        clips.append(render_block_wipe(subjudul, FONTS['subjudul'], 36, dur=2.2, base_y_ratio=0.44))

    isi_keys = sorted([k for k in data if k.startswith('Isi_')])
    for k in isi_keys:
        txt = data[k].strip()
        if not txt:
            continue
        dur = hitung_durasi_isi(txt)
        clips.append(render_block_wipe(txt, FONTS['isi'], 34, dur=dur, base_y_ratio=0.60))

    if not clips:
        # fallback kosong
        empty = ImageClip(np.zeros((VIDEO_SIZE[1], VIDEO_SIZE[0], 3), np.uint8), duration=2)
        final = empty
    else:
        final = concatenate_videoclips(clips, method="compose")

    # overlay opsional
    if os.path.exists(OVERLAY_FILE):
        try:
            overlay = ImageClip(
                np.array(Image.open(OVERLAY_FILE).convert("RGBA").resize(VIDEO_SIZE)),
                duration=final.duration
            )
            return CompositeVideoClip([final, overlay], size=VIDEO_SIZE)
        except Exception as e:
            print("overlay fail:", e)
            return final
    return final

# ==========================================================
# MAIN
# ==========================================================
if __name__ == "__main__":
    if not os.path.exists("data_berita.txt"):
        print("❌ File data_berita.txt tidak ditemukan!")
        sys.exit(1)

    berita_list = baca_semua_berita_stable("data_berita.txt")
    if not berita_list:
        print("❌ Tidak ada berita valid dalam data_berita.txt")
        sys.exit(1)

    for i, b in enumerate(berita_list, 1):
        print(f"🎬 Render {i}: {b.get('Judul','(Tanpa Judul)')}")
        clip = buat_video_stable(b)
        out = f"output_video_{i}.mp4"
        clip.write_videofile(out, fps=FPS)
        print(f"✅ Selesai: {out}")
