# ==========================================================
# ✅ VIDEO GENERATOR BETA (FINAL STABLE WITH HIGHLIGHT)
# ==========================================================
from moviepy.editor import ImageClip, CompositeVideoClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import os, re, sys, traceback, time

# ---------- KONFIGURASI ----------
VIDEO_SIZE = (720, 1280)
BG_COLOR = (0, 0, 0)
TEXT_COLOR = (255, 255, 255, 255)
FPS = 24

FONTS = {
    "upper": "ProximaNova-Bold.ttf",
    "judul": "DMSerifDisplay-Regular.ttf",
    "subjudul": "ProximaNova-Regular.ttf",
    "isi": "Poppins-Bold.ttf",
}

OVERLAY_FILE = "semangat.png"
HIGHLIGHT_COLOR = (0, 124, 188, 255)

# ---------- FONT UTILITY ----------
def load_font_safe(font_path, size):
    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        print(f"⚠️ Gagal memuat font {font_path}, fallback default")
        return ImageFont.load_default()

# ==========================================================
#  STABLE TEXT PROCESSOR DENGAN HIGHLIGHT ANIMASI
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

    # ---------- PARSER [[highlight]] ----------
    def parse_text_with_highlights(self, text):
        try:
            parts = re.split(r'(\[\[.*?\]\])', text)
            segs = []
            for part in parts:
                if part.startswith('[[') and part.endswith(']]'):
                    segs.append({'text': part[2:-2].replace('|', ' '), 'is_highlight': True})
                elif part.strip():
                    segs.append({'text': part.replace('|', ' '), 'is_highlight': False})
            return segs or [{'text': text, 'is_highlight': False}]
        except Exception:
            return [{'text': text, 'is_highlight': False}]

    # ---------- WRAPPING ----------
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
        if cur_line: lines.append(cur_line)
        return lines

    # ---------- RENDER HIGHLIGHT ----------
    def render_lines_with_continuous_highlight(self, lines, base_y, frame_idx, total_frames):
        try:
            base = Image.new("RGBA", VIDEO_SIZE, BG_COLOR + (255,))
            hl_layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
            txt_layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
            hld = ImageDraw.Draw(hl_layer)
            td = ImageDraw.Draw(txt_layer)

            progress = min(1.0, frame_idx / max(1, total_frames * 0.25))
            all_segments, total_chars = [], 0
            y = base_y
            for line in lines:
                x = self.margin_x
                for w in line:
                    if w['is_highlight']:
                        width = self._get_text_width(w['word'] + " ")
                        all_segments.append({
                            'x': x, 'y': y, 'width': width,
                            'word': w['word'], 'start': total_chars,
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
                    p = 1 - pow(1 - (chars / L if L else 1), 2)
                    w = seg['width'] * min(1, p)
                    hld.rectangle([seg['x']-4, seg['y']+4,
                                   seg['x']+w, seg['y']+self.line_height+4],
                                  fill=HIGHLIGHT_COLOR)

            y = base_y
            for line in lines:
                x = self.margin_x
                for w in line:
                    td.text((x, y), w['word'] + " ", font=self.font, fill=TEXT_COLOR)
                    x += self._get_text_width(w['word'] + " ")
                y += self.line_height

            return np.array(Image.alpha_composite(Image.alpha_composite(base, hl_layer), txt_layer).convert("RGB"))
        except Exception as e:
            print("⚠️ render highlight:", e)
            return np.zeros((VIDEO_SIZE[1], VIDEO_SIZE[0], 3), np.uint8)

# ==========================================================
#  ADAPTIVE LAYOUT DAN RENDER
# ==========================================================
def calculate_adaptive_layout(text, font_path, font_size, margin_x):
    font = load_font_safe(font_path, font_size)
    proc = StableTextProcessor(font, VIDEO_SIZE[0], margin_x)
    lines = proc.smart_wrap_with_highlights(text)
    base_y = int(VIDEO_SIZE[1] * 0.60)
    total_h = len(lines) * proc.line_height
    batas_bawah = VIDEO_SIZE[1] - 180
    if base_y + total_h > batas_bawah:
        base_y -= min(base_y - 80, (base_y + total_h - batas_bawah) + 20)
    return {'lines': lines, 'font': font, 'processor': proc, 'base_y': base_y}

# ==========================================================
#  RENDER TEKS BLOCK
# ==========================================================
def render_text_block_stable(text, font_path, font_size, dur):
    total_frames = int(FPS * dur)
    margin_x = 70
    layout = calculate_adaptive_layout(text, font_path, font_size, margin_x)
    proc = layout['processor']
    lines, base_y = layout['lines'], layout['base_y']

    frames = []
    for i in range(total_frames):
        frame = proc.render_lines_with_continuous_highlight(lines, base_y, i, total_frames)
        frames.append(frame)
    return concatenate_videoclips([ImageClip(f, duration=1/FPS) for f in frames], method="compose")

# ==========================================================
#  OPENING & SEPARATOR & OVERLAY
# ==========================================================
def render_opening_stable(upper, judul, subjudul, fonts):
    font_j = load_font_safe(fonts['judul'], 54)
    proc = StableTextProcessor(font_j, VIDEO_SIZE[0])
    lines = proc.smart_wrap_with_highlights(judul)
    total_frames = int(FPS * 3)
    frames = [proc.render_lines_with_continuous_highlight(lines, 700, i, total_frames)
              for i in range(total_frames)]
    return concatenate_videoclips([ImageClip(f, duration=1/FPS) for f in frames], method="compose")

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
#  PARSER & DURASI
# ==========================================================
def baca_semua_berita_stable(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()
        data, cur, i = [], {}, 1
        for l in lines:
            if l.startswith("Judul:"):
                if cur: data.append(cur)
                cur = {'Judul': l[6:].strip()}
            elif l.startswith("Isi:"):
                cur[f'Isi_{i}'] = l[4:].strip(); i += 1
        if cur: data.append(cur)
        return data
    except Exception as e:
        print("parse fail:", e)
        return []

def hitung_durasi_isi(text):
    clean = re.sub(r'\[\[.*?\]\]', lambda m: m.group(0)[2:-2], text)
    words = len(clean.split())
    dur = (words / 160) * 60
    return round(max(3, min(10, dur)) + 1.5, 1)

# ==========================================================
#  MAIN VIDEO BUILDER
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
#  MAIN EXECUTION: BACA FILE DATA_BERITA.TXT
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
