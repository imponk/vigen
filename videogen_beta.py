# ==========================================================
# ✅ VIDEO GENERATOR FINAL V6
# Semua teks (judul, subjudul, isi) muncul sapuan kiri→kanan
# ==========================================================
from moviepy.editor import ImageClip, CompositeVideoClip, concatenate_videoclips, VideoClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import os, re, sys

VIDEO_SIZE = (720, 1280)
BG_COLOR = (0, 0, 0)
TEXT_COLOR = (255, 255, 255, 255)
FPS = 60
HIGHLIGHT_COLOR = (0, 124, 188, 255)
OVERLAY_FILE = "semangat.png"

FONTS = {
    "upper": "ProximaNova-Bold.ttf",
    "judul": "DMSerifDisplay-Regular.ttf",
    "subjudul": "ProximaNova-Regular.ttf",
    "isi": "Poppins-Bold.ttf",
}

def load_font_safe(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        print(f"⚠️ Font gagal dimuat: {path}")
        return ImageFont.load_default()

# ==========================================================
# EASING FUNGSI (halus seperti sapuan judul)
# ==========================================================
def ease_sweep(t: float):
    # mirip animasi judul: lambat di awal & akhir, cepat di tengah
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
                segs.append({'text': p[2:-2].replace('|',' '), 'is_highlight': True})
            elif p.strip():
                segs.append({'text': p.replace('|',' '), 'is_highlight': False})
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
                cur.append(wi)
                cur_w += wlen
            else:
                lines.append(cur)
                cur, cur_w = [wi], wlen
        if cur:
            lines.append(cur)
        return lines

    # ======================================================
    # RENDER DENGAN SAPUAN HALUS
    # ======================================================
    def render_lines_with_progress(self, lines, base_y, progress):
        base = Image.new("RGBA", VIDEO_SIZE, BG_COLOR + (255,))
        hl_layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
        txt_layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
        hld = ImageDraw.Draw(hl_layer)
        td = ImageDraw.Draw(txt_layer)

        total_w = max(sum(self._get_text_width(w['word'] + " ") for w in line)
                      for line in lines)
        sweep_x = int(total_w * ease_sweep(progress))

        y = base_y
        for line in lines:
            x = self.margin_x
            for w in line:
                width = self._get_text_width(w['word'] + " ")
                right_edge = x + width
                # highlight sapuan
                if w['is_highlight'] and right_edge <= self.margin_x + sweep_x:
                    for i in range(3):
                        offset = i * 0.4
                        alpha = int(255 * (1 - 0.3 * i))
                        hld.rectangle(
                            [x0 := x - 4 + offset,
                             seg_y := y + 4,
                             x1 := right_edge + offset,
                             seg_y + self.line_height + 4],
                            fill=(HIGHLIGHT_COLOR[0], HIGHLIGHT_COLOR[1], HIGHLIGHT_COLOR[2], alpha)
                        )
                # teks muncul seiring sapuan
                if right_edge <= self.margin_x + sweep_x:
                    td.text((x, y), w['word'] + " ", font=self.font, fill=TEXT_COLOR)
                x = right_edge
            y += self.line_height

        frame = Image.alpha_composite(
            Image.alpha_composite(base, hl_layer), txt_layer).convert("RGB")
        return np.array(frame)

# ==========================================================
# LAYOUT DAN VIDEO RENDER
# ==========================================================
def calculate_adaptive_layout(text, font_path, size, margin_x):
    font = load_font_safe(font_path, size)
    proc = StableTextProcessor(font, VIDEO_SIZE[0], margin_x)
    lines = proc.smart_wrap_with_highlights(text)
    base_y = int(VIDEO_SIZE[1] * 0.6)
    total_h = len(lines) * proc.line_height
    if base_y + total_h > VIDEO_SIZE[1] - 180:
        base_y -= (base_y + total_h - (VIDEO_SIZE[1] - 180))
    return {'lines': lines, 'font': font, 'processor': proc, 'base_y': base_y}

def render_text_block_stable(text, font_path, size, dur):
    layout = calculate_adaptive_layout(text, font_path, size, 70)
    proc, lines, base_y = layout['processor'], layout['lines'], layout['base_y']
    def make_frame(t):
        p = min(1.0, t / dur)
        return proc.render_lines_with_progress(lines, base_y, p)
    return VideoClip(make_frame, duration=dur).set_fps(FPS)

# ==========================================================
# PARSER MULTILINE
# ==========================================================
def baca_semua_berita_stable(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()
        data, current, key, isi_count, buf = [], {}, None, 1, []

        def commit():
            nonlocal buf, key, current
            if key and buf:
                current[key] = (current.get(key, "") + " " + " ".join(buf)).strip()
            buf = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("Judul:"):
                commit()
                if current: data.append(current); current = {}; isi_count = 1
                key = "Judul"; content = line.replace("Judul:", "").strip()
                buf = [content] if content else []
                continue
            if line.startswith("Subjudul:"):
                commit(); key = "Subjudul"
                content = line.replace("Subjudul:", "").strip()
                buf = [content] if content else []
                continue
            if line.startswith("Isi:"):
                commit(); key = f"Isi_{isi_count}"; isi_count += 1
                content = line.replace("Isi:", "").strip()
                buf = [content] if content else []
                continue
            buf.append(line)
        commit()
        if current: data.append(current)
        return data
    except Exception as e:
        print("parse fail:", e); return []

# ==========================================================
# VIDEO BUILDER
# ==========================================================
def buat_video_stable(data):
    clips = []
    if data.get('Judul'):
        clips.append(render_text_block_stable(data['Judul'], FONTS['judul'], 54, 3))
    if data.get('Subjudul'):
        clips.append(render_text_block_stable(data['Subjudul'], FONTS['subjudul'], 36, 2.5))
    isi_keys = sorted([k for k in data if k.startswith('Isi_')])
    for k in isi_keys:
        dur = max(3, len(data[k].split()) / 25)
        clips.append(render_text_block_stable(data[k], FONTS['isi'], 34, dur))
    final = concatenate_videoclips(clips, method="compose")
    if os.path.exists(OVERLAY_FILE):
        overlay = ImageClip(np.array(Image.open(OVERLAY_FILE).convert("RGBA").resize(VIDEO_SIZE)),
                            duration=final.duration)
        return CompositeVideoClip([final, overlay], size=VIDEO_SIZE)
    return final

# ==========================================================
# MAIN EXECUTION
# ==========================================================
if __name__ == "__main__":
    if not os.path.exists("data_berita.txt"):
        print("❌ File data_berita.txt tidak ditemukan!"); sys.exit(1)

    berita_list = baca_semua_berita_stable("data_berita.txt")
    if not berita_list:
        print("❌ Tidak ada berita valid"); sys.exit(1)

    for i, b in enumerate(berita_list, 1):
        print(f"🎬 Membuat video {i}: {b.get('Judul','(Tanpa Judul)')}")
        clip = buat_video_stable(b)
        out = f"output_video_{i}.mp4"
        clip.write_videofile(out, fps=FPS)
        print(f"✅ Selesai: {out}\n")
