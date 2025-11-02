# ==========================================================
# ✅ VIDEO GENERATOR FINAL V9
# Urutan: Upper → (pause) → Judul → (pause) → Subjudul → (pause) → Isi
# Wipe kiri→kanan satu blok; highlight solid hanya pada [[...]]
# ==========================================================
from moviepy.editor import ImageClip, CompositeVideoClip, concatenate_videoclips, VideoClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import os, re, sys

# ---------- KONFIG ----------
VIDEO_SIZE = (720, 1280)  # (W, H)
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

# Timing (detik)
PAUSE_BETWEEN = 0.40        # jeda kecil antar segmen
DUR_UPPER = 1.60            # durasi wipe Upper (singkat)
DUR_JUDUL = 2.20            # durasi wipe Judul (lebih elegan)
DUR_SUBJUDUL = 1.80         # durasi wipe Subjudul
DUR_ISI_SWEEP = 1.00        # durasi sapu cepat Isi (wipe), sisanya hold sesuai panjang
MIN_ISI_TOTAL = 3.0         # total durasi minimal tiap blok isi (sweep + hold)
MAX_ISI_TOTAL = 14.0

# ---------- UTIL ----------
def load_font_safe(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        print(f"⚠️ Font gagal dimuat: {path} → fallback default")
        return ImageFont.load_default()

def ease_sweep(t: float):
    # Easing mirip “mask reveal” halus (lambat di awal/akhir, cepat di tengah)
    t = max(0.0, min(1.0, t))
    return 1 - pow(1 - pow(t, 1.5), 3)

# ==========================================================
# TEXT PROCESSOR
# ==========================================================
class StableTextProcessor:
    def __init__(self, font, max_width, margin_x=72):
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
            return len(text) * 15  # fallback kira-kira

    def parse_text_with_highlights(self, text):
        # Segmentasi: [[...]] = highlight, lainnya biasa. | diubah spasi.
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
            chunk = s['text'].split()
            for w in chunk:
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

    # ---------- BANGUN PETA KOORDINAT (untuk wipe global & highlight per segmen) ----------
    def layout_lines(self, lines, base_y):
        """
        return:
          - line_rects: [(x0, x1, y0, y1), ...] per baris
          - word_rects: [{'x0','x1','y0','y1','is_highlight'}, ...] dalam urutan teks
          - block_bbox: (min_x, max_x, min_y, max_y) mencakup semua baris
        """
        line_rects, word_rects = [], []
        y = base_y
        min_x = None
        max_x = None
        for line in lines:
            x = self.margin_x
            line_x0 = x
            for w in line:
                width = int(self._get_text_width(w['word'] + " "))
                word_rects.append({
                    'x0': x, 'x1': x + width,
                    'y0': y, 'y1': y + self.line_height,
                    'is_highlight': w['is_highlight']
                })
                x += width
            line_x1 = x
            line_rects.append((line_x0, line_x1, y, y + self.line_height))
            min_x = line_x0 if min_x is None else min(min_x, line_x0)
            max_x = line_x1 if max_x is None else max(max_x, line_x1)
            y += self.line_height
        min_y = base_y
        max_y = y
        block_bbox = (min_x or self.margin_x, max_x or self.margin_x, min_y, max_y)
        return line_rects, word_rects, block_bbox

    # ---------- RENDER: WIPE GLOBAL + HIGHLIGHT SEGMENTED ----------
    def render_block_with_global_wipe(self, text, progress, base_y,
                                      draw_highlight=True, solid_block=False):
        """
        - Global sweep: posisi batas X = block_x0 + progress * total_width.
        - Jika draw_highlight=True: gambar blok biru solid hanya di area kata yang ditandai,
          namun dibatasi oleh sweep (ikut mask sapuan).
        - Jika solid_block=True: isi seluruh area baris yang sudah tersapu dengan blok biru penuh (jarang dipakai).
        """
        lines = self.smart_wrap_with_highlights(text)
        base = Image.new("RGBA", VIDEO_SIZE, BG_COLOR + (255,))
        hl_layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
        txt_layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
        hld = ImageDraw.Draw(hl_layer)
        td = ImageDraw.Draw(txt_layer)

        # Susun koordinat
        line_rects, word_rects, (bx0, bx1, by0, by1) = self.layout_lines(lines, base_y)
        total_w = max(1, bx1 - bx0)
        sweep_x = bx0 + int(total_w * ease_sweep(progress))

        # 1) Gambar highlight per-kata yang ditandai, dibatasi sweep
        if draw_highlight:
            for wr in word_rects:
                if wr['is_highlight']:
                    x0 = max(wr['x0'] - 3, bx0 - 3)
                    x1 = min(wr['x1'], sweep_x)
                    if x1 > x0:
                        hld.rectangle([x0, wr['y0'] + 4, x1, wr['y1'] + 4], fill=HIGHLIGHT_COLOR)

        # (opsional) blok solid penuh di area tersapu — TIDAK dipakai default
        if solid_block:
            x0 = bx0 - 4
            x1 = sweep_x
            if x1 > x0:
                hld.rectangle([x0, by0 - 4, x1, by1 + 4], fill=HIGHLIGHT_COLOR)

        # 2) Gambar teks penuh → lalu mask dengan sweep global
        for wr in word_rects:
            td.text((wr['x0'], wr['y0']), " ", font=self.font, fill=TEXT_COLOR)  # spacer (tak wajib)
        for line in lines:
            x = self.margin_x
            for w in line:
                td.text((x, line_rects[lines.index(line)][2]), w['word'] + " ", font=self.font, fill=TEXT_COLOR)
                x += int(self._get_text_width(w['word'] + " "))

        # Mask global untuk teks: hanya bagian tersapu yang terlihat
        mask = Image.new("L", VIDEO_SIZE, 0)
        mdraw = ImageDraw.Draw(mask)
        mdraw.rectangle([bx0 - 2, by0 - 6, sweep_x + 2, by1 + 6], fill=255)
        txt_visible = Image.composite(txt_layer, Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0)), mask)

        frame = Image.alpha_composite(Image.alpha_composite(base, hl_layer), txt_visible).convert("RGB")
        return np.array(frame)

# ==========================================================
# LAYOUT + VIDEO GENERATORS
# ==========================================================
def build_block_clip(text, font_path, size, base_y_ratio, dur_wipe, *,
                     draw_highlight=True, solid_block=False, hold_extra=0.0, is_isi=False):
    """
    - dur_wipe: durasi sapuan (detik)
    - draw_highlight: True → highlight hanya untuk [[...]], ikut sweep
    - solid_block: True → block biru penuh area tersapu (umumnya False sesuai permintaan)
    - hold_extra: waktu tambahan menahan tampilan setelah sapuan selesai
    - is_isi: bila True → durasi total disesuaikan panjang teks (sweep + hold otomatis)
    """
    font = load_font_safe(font_path, size)
    proc = StableTextProcessor(font, VIDEO_SIZE[0], margin_x=72)

    # Tempatkan:
    if is_isi:
        base_y = int(VIDEO_SIZE[1] * 0.60)
    else:
        # Upper/Title/Subjudul sedikit lebih atas agar komposisi nyaman
        base_y = int(VIDEO_SIZE[1] * (0.34 if font_path == FONTS['judul'] else (0.42 if font_path == FONTS['subjudul'] else 0.28)))

    # durasi total
    if is_isi:
        words = len(re.sub(r'\[\[.*?\]\]', lambda m: m.group(0)[2:-2], text).split())
        hold_auto = max(0.0, min(MAX_ISI_TOTAL - dur_wipe, words / 16.0))
        dur_total = max(MIN_ISI_TOTAL, dur_wipe + hold_auto)
    else:
        dur_total = dur_wipe + max(0.0, hold_extra)

    def make_frame(t):
        if t <= dur_wipe:
            p = ease_sweep(t / dur_wipe)
        else:
            p = 1.0
        return proc.render_block_with_global_wipe(
            text, p, base_y,
            draw_highlight=draw_highlight,
            solid_block=solid_block
        )

    return VideoClip(make_frame, duration=dur_total).set_fps(FPS)

def pause_clip(dur=PAUSE_BETWEEN):
    return ImageClip(np.zeros((VIDEO_SIZE[1], VIDEO_SIZE[0], 3), np.uint8), duration=dur)

# ==========================================================
# PARSER MULTI-BARIS (Upper/Judul/Subjudul/Isi)
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

            if line.startswith("Upper:"):
                commit()
                key = "Upper"
                content = line.replace("Upper:", "").strip()
                buf = [content] if content else []
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

            buf.append(line)

        commit()
        if current:
            data.append(current)
        return data
    except Exception as e:
        print("parse fail:", e)
        return []

# ==========================================================
# BUILD VIDEO URUTAN SESUAI CONTOH
# ==========================================================
def buat_video_stable(data):
    clips = []

    upper = data.get('Upper', '').strip()
    judul = data.get('Judul', '').strip()
    subjudul = data.get('Subjudul', '').strip()

    # 1) Upper (jika ada)
    if upper:
        clips.append(build_block_clip(upper, FONTS['upper'], 28, base_y_ratio=0.28,
                                      dur_wipe=DUR_UPPER, draw_highlight=False, hold_extra=0.2))
        clips.append(pause_clip())

    # 2) Judul
    if judul:
        clips.append(build_block_clip(judul, FONTS['judul'], 56, base_y_ratio=0.34,
                                      dur_wipe=DUR_JUDUL, draw_highlight=False, hold_extra=0.20))
        clips.append(pause_clip())

    # 3) Subjudul
    if subjudul:
        clips.append(build_block_clip(subjudul, FONTS['subjudul'], 36, base_y_ratio=0.42,
                                      dur_wipe=DUR_SUBJUDUL, draw_highlight=False, hold_extra=0.20))
        clips.append(pause_clip())

    # 4) Isi (bisa banyak paragraf) — sapuan cepat 1 detik, highlight hanya [[...]]
    isi_keys = sorted([k for k in data if k.startswith('Isi_')])
    for k in isi_keys:
        txt = data[k].strip()
        if not txt:
            continue
        clips.append(build_block_clip(txt, FONTS['isi'], 34, base_y_ratio=0.60,
                                      dur_wipe=DUR_ISI_SWEEP, draw_highlight=True,
                                      solid_block=False, is_isi=True))
        clips.append(pause_clip(0.25))  # jeda antar isi sedikit lebih pendek

    # Gabung
    if not clips:
        final = ImageClip(np.zeros((VIDEO_SIZE[1], VIDEO_SIZE[0], 3), np.uint8), duration=2)
    else:
        final = concatenate_videoclips(clips, method="compose")

    # Overlay (opsional)
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
