# ==========================================================
# ✅ VIDEO GENERATOR BETA FINAL V4
# (MoviePy-native smooth highlight animation)
# ==========================================================
from moviepy.editor import ImageClip, CompositeVideoClip, concatenate_videoclips, VideoClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import os, re, sys

# ---------- KONFIGURASI ----------
VIDEO_SIZE = (720, 1280)
BG_COLOR = (0, 0, 0)
TEXT_COLOR = (255, 255, 255, 255)
FPS = 30  # fps lebih tinggi agar smooth
HIGHLIGHT_COLOR = (0, 124, 188, 255)
OVERLAY_FILE = "semangat.png"

FONTS = {
    "upper": "ProximaNova-Bold.ttf",
    "judul": "DMSerifDisplay-Regular.ttf",
    "subjudul": "ProximaNova-Regular.ttf",
    "isi": "Poppins-Bold.ttf",
}

# ---------- FONT UTILITY ----------
def load_font_safe(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        print(f"⚠️ Gagal memuat font {path}, fallback default")
        return ImageFont.load_default()

# ==========================================================
#  STABLE TEXT PROCESSOR (HALUS)
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
            bbox = self.font.getbbox("Hgjypq")
            return max(bbox[3] - bbox[1] + 8, 30)
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
        lines, cur_line, cur_w = [], [], 0
        avail = self.max_width - self.margin_x - self.margin_right
        for wi in words:
            wlen = self._get_text_width(wi['word'] + " ")
            if cur_w + wlen <= avail:
                cur_line.append(wi)
                cur_w += wlen
            else:
                lines.append(cur_line)
                cur_line = [wi]
                cur_w = wlen
        if cur_line:
            lines.append(cur_line)
        return lines

    # ======================================================
    #   HALUS: CONTINUOUS HIGHLIGHT ANIMATION
    # ======================================================
    def render_lines_with_progress(self, lines, base_y, progress):
        base = Image.new("RGBA", VIDEO_SIZE, BG_COLOR + (255,))
        hl_layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
        txt_layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
        hld = ImageDraw.Draw(hl_layer)
        td = ImageDraw.Draw(txt_layer)

        all_segments = []
        total_chars = 0
        y = base_y

        for line in lines:
            x = self.margin_x
            for w in line:
                if w['is_highlight']:
                    width = self._get_text_width(w['word'] + " ")
                    all_segments.append({
                        'x': x,
                        'y': y,
                        'width': width,
                        'word': w['word'],
                        'start': total_chars,
                        'end': total_chars + len(w['word'])
                    })
                    total_chars += len(w['word']) + 1
                x += self._get_text_width(w['word'] + " ")
            y += self.line_height

        cur_chars = int(progress * total_chars)
        for seg in all_segments:
            if seg['start'] <= cur_chars:
                chars = max(0, cur_chars - seg['start'])
                L = len(seg['word'])
                t = min(1.0, chars / float(L) if L else 1)
                smooth = 1 - pow(1 - t, 3)  # cubic easing
                w = seg['width'] * smooth
                if w > 0:
                    x0 = seg['x'] - 4
                    x1 = seg['x'] + w
                    if x1 > x0:
                        hld.rectangle([x0, seg['y'] + 4,
                                       x1, seg['y'] + self.line_height + 4],
                                      fill=HIGHLIGHT_COLOR)

        # teks
        y = base_y
        for line in lines:
            x = self.margin_x
            for w in line:
                td.text((x, y), w['word'] + " ", font=self.font, fill=TEXT_COLOR)
                x += self._get_text_width(w['word'] + " ")
            y += self.line_height

        return np.array(Image.alpha_composite(
            Image.alpha_composite(base, hl_layer), txt_layer).convert("RGB"))

# ==========================================================
#  ADAPTIVE LAYOUT DAN RENDER
# ==========================================================
def calculate_adaptive_layout(text, font_path, size, margin_x):
    font = load_font_safe(font_path, size)
    proc = StableTextProcessor(font, VIDEO_SIZE[0], margin_x)
    lines = proc.smart_wrap_with_highlights(text)
    base_y = int(VIDEO_SIZE[1] * 0.65)
    total_h = len(lines) * proc.line_height
    batas_bawah = VIDEO_SIZE[1] - 180
    if base_y + total_h > batas_bawah:
        base_y -= min(base_y - 80, (base_y + total_h - batas_bawah) + 20)
    return {'lines': lines, 'font': font, 'processor': proc, 'base_y': base_y}

# ==========================================================
#  SMOOTH VIDEO RENDER MENGGUNAKAN make_frame
# ==========================================================
def render_text_block_stable(text, font_path, size, dur):
    layout = calculate_adaptive_layout(text, font_path, size, 70)
    proc, lines, base_y = layout['processor'], layout['lines'], layout['base_y']

    def make_frame(t):
        progress = min(1.0, t / dur)
        return proc.render_lines_with_progress(lines, base_y, progress)

    return VideoClip(make_frame, duration=dur).set_fps(FPS)

# ==========================================================
#  OPENING / SEPARATOR / OVERLAY
# ==========================================================
def render_opening_stable(upper, judul, subjudul, fonts):
    font_j = load_font_safe(fonts['judul'], 54)
    proc = StableTextProcessor(font_j, VIDEO_SIZE[0])
    lines = proc.smart_wrap_with_highlights(judul)

    def make_frame_j(t):
        progress = min(1.0, t / 3.0)
        return proc.render_lines_with_progress(lines, 380, progress)

    clip_j = VideoClip(make_frame_j, duration=3).set_fps(FPS)

    if subjudul:
        font_s = load_font_safe(fonts['subjudul'], 36)
        proc2 = StableTextProcessor(font_s, VIDEO_SIZE[0])
        lines2 = proc2.smart_wrap_with_highlights(subjudul)

        def make_frame_s(t):
            progress = min(1.0, t / 3.0)
            base = Image.fromarray(proc.render_lines_with_progress(lines, 380, progress))
            sub = Image.fromarray(proc2.render_lines_with_progress(lines2, 470, progress))
            return np.array(Image.alpha_composite(base.convert("RGBA"), sub.convert("RGBA")).convert("RGB"))

        return VideoClip(make_frame_s, duration=3).set_fps(FPS)

    return clip_j

def render_separator_stable(dur=0.7):
    return ImageClip(np.zeros((VIDEO_SIZE[1], VIDEO_SIZE[0], 3), np.uint8), duration=dur)

def add_overlay(base_clip):
    if not os.path.exists(OVERLAY_FILE):
        return base_clip
    try:
        overlay = ImageClip(np.array(Image.open(OVERLAY_FILE).convert("RGBA").resize(VIDEO_SIZE)),
                            duration=base_clip.duration)
        return CompositeVideoClip([base_clip, overlay], size=VIDEO_SIZE)
    except Exception as e:
        print("overlay fail:", e)
        return base_clip

# ==========================================================
#  PARSER MULTI-BARIS UNTUK JUDUL/SUBJUDUL/ISI
# ==========================================================
def baca_semua_berita_stable(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()

        data = []
        current = {}
        key = None
        isi_count = 1
        buffer = []

        def commit_buffer():
            nonlocal buffer, key, current
            if key and buffer:
                joined = " ".join(buffer).strip()
                if joined:
                    current[key] = (current.get(key, "") + " " + joined).strip()
            buffer = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("Judul:"):
                commit_buffer()
                if current:
                    data.append(current)
                    current = {}
                    isi_count = 1
                key = "Judul"
                content = line.replace("Judul:", "").strip()
                buffer = [content] if content else []
                continue

            if line.startswith("Subjudul:"):
                commit_buffer()
                key = "Subjudul"
                content = line.replace("Subjudul:", "").strip()
                buffer = [content] if content else []
                continue

            if line.startswith("Isi:"):
                commit_buffer()
                key = f"Isi_{isi_count}"
                isi_count += 1
                content = line.replace("Isi:", "").strip()
                buffer = [content] if content else []
                continue

            buffer.append(line)

        commit_buffer()
        if current:
            data.append(current)
        return data

    except Exception as e:
        print("parse fail:", e)
        return []

# ==========================================================
#  DURASI OTOMATIS BERDASARKAN JUMLAH KATA
# ==========================================================
def hitung_durasi_isi(text):
    clean = re.sub(r'\[\[.*?\]\]', lambda m: m.group(0)[2:-2], text)
    words = len(clean.split())
    dur = (words / 160) * 60
    return round(max(3, min(10, dur)) + 1.5, 1)

# ==========================================================
#  VIDEO BUILDER
# ==========================================================
def buat_video_stable(data):
    opening = render_opening_stable(data.get('Upper',''), data.get('Judul',''),
                                    data.get('Subjudul',''), FONTS)
    isi_keys = sorted([k for k in data if k.startswith('Isi_')])
    clips = [opening]
    for k in isi_keys:
        dur = hitung_durasi_isi(data[k])
        clips += [render_separator_stable(0.5),
                  render_text_block_stable(data[k], FONTS['isi'], 34, dur)]
    final = concatenate_videoclips(clips)
    return add_overlay(final)

# ==========================================================
#  MAIN EXECUTION
# ==========================================================
if __name__ == "__main__":
    if not os.path.exists("data_berita.txt"):
        print("❌ File data_berita.txt tidak ditemukan!")
        sys.exit(1)

    berita_list = baca_semua_berita_stable("data_berita.txt")
    if not berita_list:
        print("❌ Tidak ada berita valid dalam data_berita.txt")
        sys.exit(1)

    for idx, berita in enumerate(berita_list, 1):
        print(f"📰 Membuat video berita {idx}: {berita.get('Judul','(Tanpa Judul)')}")
        clip = buat_video_stable(berita)
        nama_file = f"output_video_{idx}.mp4"
        clip.write_videofile(nama_file, fps=FPS)
        print(f"✅ Selesai: {nama_file}\n")
