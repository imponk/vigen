# ==========================================================
# ✅ VIDEO GENERATOR FINAL V8
# Global sweep untuk ISI (satu kesatuan), block biru solid 100%
# Judul/Subjudul wipe halus kiri→kanan
# ==========================================================
from moviepy.editor import ImageClip, CompositeVideoClip, concatenate_videoclips, VideoClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import os, re, sys

# ---------- KONFIG ----------
VIDEO_SIZE = (720, 1280)   # (W, H)
BG_COLOR = (0, 0, 0)
TEXT_COLOR = (255, 255, 255, 255)
HIGHLIGHT_COLOR = (0, 124, 188, 255)  # solid 100%
FPS = 60
OVERLAY_FILE = "semangat.png"

FONTS = {
    "upper": "ProximaNova-Bold.ttf",
    "judul": "DMSerifDisplay-Regular.ttf",
    "subjudul": "ProximaNova-Regular.ttf",
    "isi": "Poppins-Bold.ttf",
}

# Durasi (detik)
DUR_JUDUL = 2.6
DUR_SUBJUDUL = 2.0
# Sweep cepat untuk ISI — blok global
DUR_ISI_SWEEP = 1.0  # 1 detik sapu cepat; sisanya hold

# ---------- UTIL ----------
def load_font_safe(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        print(f"⚠️ Font gagal dimuat: {path} → fallback default")
        return ImageFont.load_default()

def ease_sweep(t: float):
    # Easing lembut (mask reveal): lambat awal/akhir, cepat tengah
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
            return len(text) * 15

    def parse_text_with_highlights(self, text):
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

    # ------------- RENDER: WIPE PER BARIS (JUDUL/SUBJUDUL) -------------
    def render_lines_wipe_per_line(self, lines, base_y, progress):
        base = Image.new("RGBA", VIDEO_SIZE, BG_COLOR + (255,))
        txt_layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
        td = ImageDraw.Draw(txt_layer)

        y = base_y
        # Hitung total lebar baris untuk sapuan
        line_widths = []
        for line in lines:
            wsum = sum(int(self._get_text_width(w['word'] + " ")) for w in line)
            line_widths.append(wsum)

        for idx, line in enumerate(lines):
            line_total_w = line_widths[idx]
            sweep = int(line_total_w * ease_sweep(progress))
            # Gambar teks penuh pada layer baris, lalu mask area sweep
            line_img = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
            ltd = ImageDraw.Draw(line_img)

            x = self.margin_x
            for w in line:
                ltd.text((x, y), w['word'] + " ", font=self.font, fill=TEXT_COLOR)
                x += int(self._get_text_width(w['word'] + " "))

            # Mask batas sweep
            if sweep > 0:
                mask = Image.new("L", VIDEO_SIZE, 0)
                mdraw = ImageDraw.Draw(mask)
                mdraw.rectangle([self.margin_x - 2, y - 2,
                                 self.margin_x + sweep + 2, y + self.line_height + 10], fill=255)
                txt_layer = Image.composite(line_img, txt_layer, mask)

            y += self.line_height

        frame = Image.alpha_composite(base, txt_layer).convert("RGB")
        return np.array(frame)

    # ------------- RENDER: GLOBAL SWEEP + BLOCK BIRU SOLID (ISI) -------------
    def render_lines_wipe_global_block(self, lines, base_y, progress):
        """
        Satu sapuan global untuk seluruh blok ISI:
        - gambar block biru solid 100% yang mengikuti sweep (global width)
        - lalu teks di atasnya, dibatasi oleh mask sweep yang sama
        """
        base = Image.new("RGBA", VIDEO_SIZE, BG_COLOR + (255,))
        txt_layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
        td = ImageDraw.Draw(txt_layer)

        # Hitung bounding box seluruh teks (global) untuk ukuran sweep
        min_x = self.margin_x
        max_x = self.margin_x
        y = base_y
        for line in lines:
            line_w = sum(int(self._get_text_width(w['word'] + " ")) for w in line)
            max_x = max(max_x, self.margin_x + line_w)
            y += self.line_height
        min_y = base_y
        max_y = y

        total_w = max_x - min_x
        sweep = int(total_w * ease_sweep(progress))

        # 1) Gambar BLOCK BIRU SOLID (100%) sesuai sweep (global)
        if sweep > 0:
            block = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
            bd = ImageDraw.Draw(block)
            bd.rectangle([min_x - 4, min_y - 4,
                          min_x + sweep, max_y + 4],
                         fill=HIGHLIGHT_COLOR)  # solid RGBA
            base = Image.alpha_composite(base, block)

        # 2) Gambar teks penuh pada layer, lalu batasi dengan mask sweep global
        y = base_y
        for line in lines:
            x = self.margin_x
            for w in line:
                td.text((x, y), w['word'] + " ", font=self.font, fill=TEXT_COLOR)
                x += int(self._get_text_width(w['word'] + " "))
            y += self.line_height

        if sweep > 0:
            mask = Image.new("L", VIDEO_SIZE, 0)
            mdraw = ImageDraw.Draw(mask)
            mdraw.rectangle([min_x - 2, min_y - 6,
                             min_x + sweep + 2, max_y + 6], fill=255)
            txt_layer = Image.composite(txt_layer, Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0)), mask)

        frame = Image.alpha_composite(base, txt_layer).convert("RGB")
        return np.array(frame)

# ==========================================================
# LAYOUT + VIDEO GENERATORS
# ==========================================================
def calculate_adaptive_layout(text, font_path, size, margin_x, base_y_ratio):
    font = load_font_safe(font_path, size)
    proc = StableTextProcessor(font, VIDEO_SIZE[0], margin_x)
    lines = proc.smart_wrap_with_highlights(text)
    base_y = int(VIDEO_SIZE[1] * base_y_ratio)
    total_h = len(lines) * proc.line_height
    batas_bawah = VIDEO_SIZE[1] - 160
    if base_y + total_h > batas_bawah:
        base_y = max(80, base_y - (base_y + total_h - batas_bawah))
    return {'lines': lines, 'processor': proc, 'base_y': base_y}

def render_block_wipe_title(text, font_path, size, dur, base_y_ratio):
    lay = calculate_adaptive_layout(text, font_path, size, 70, base_y_ratio)
    proc, lines, base_y = lay['processor'], lay['lines'], lay['base_y']
    def make_frame(t):
        p = ease_sweep(min(1.0, t / dur))
        return proc.render_lines_wipe_per_line(lines, base_y, p)
    return VideoClip(make_frame, duration=dur).set_fps(FPS)

def render_block_wipe_isi_global(text, font_path, size, dur_sweep, base_y_ratio):
    """
    ISI: sapuan cepat (dur_sweep), lalu hold hingga akhir durasi (auto).
    Durasi total dihitung dari panjang teks (hold).
    """
    # Hitung durasi total isi (hold setelah sweep)
    words = len(re.sub(r'\[\[.*?\]\]', lambda m: m.group(0)[2:-2], text).split())
    dur_total = max(dur_sweep + 1.5, min(14.0, words / 16.0))  # sweep cepat + baca nyaman

    lay = calculate_adaptive_layout(text, font_path, size, 70, base_y_ratio)
    proc, lines, base_y = lay['processor'], lay['lines'], lay['base_y']

    def make_frame(t):
        if t <= dur_sweep:
            p = ease_sweep(t / dur_sweep)
        else:
            p = 1.0  # sudah tersapu penuh → block biru penuh + teks penuh
        return proc.render_lines_wipe_global_block(lines, base_y, p)

    return VideoClip(make_frame, duration=dur_total).set_fps(FPS)

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

            # lanjutan baris sebelumnya
            buf.append(line)

        commit()
        if current:
            data.append(current)
        return data
    except Exception as e:
        print("parse fail:", e)
        return []

# ==========================================================
# BUILD VIDEO
# ==========================================================
def buat_video_stable(data):
    clips = []

    judul = data.get('Judul', '').strip()
    subjudul = data.get('Subjudul', '').strip()

    if judul:
        clips.append(render_block_wipe_title(judul, FONTS['judul'], 54, DUR_JUDUL, base_y_ratio=0.34))
    if subjudul:
        clips.append(render_block_wipe_title(subjudul, FONTS['subjudul'], 36, DUR_SUBJUDUL, base_y_ratio=0.42))

    isi_keys = sorted([k for k in data if k.startswith('Isi_')])
    for k in isi_keys:
        txt = data[k].strip()
        if not txt:
            continue
        # ISI: sapuan global cepat (block biru solid 100% + teks)
        clips.append(render_block_wipe_isi_global(txt, FONTS['isi'], 34, DUR_ISI_SWEEP, base_y_ratio=0.60))

    final = concatenate_videoclips(clips, method="compose") if clips else ImageClip(
        np.zeros((VIDEO_SIZE[1], VIDEO_SIZE[0], 3), np.uint8), duration=2)

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
