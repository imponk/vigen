# ==========================================================
# ✅ VIDEO GENERATOR - MULTILINE SMOOTH HIGHLIGHT (READY-TO-USE)
# ==========================================================
from moviepy.editor import ImageClip, CompositeVideoClip, concatenate_videoclips, VideoClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import os
import re
import sys
import time
import traceback

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

# Highlight config
HIGHLIGHT_COLOR = (0, 124, 188, 255)
ISILINE_PADDING = 5  # Jarak vertikal antar baris isi

# ---------- UTIL: FONT AMAN ----------
def load_font_safe(font_path, size):
    try:
        font = ImageFont.truetype(font_path, size)
        # Sanity test
        dummy = Image.new("RGB", (100, 40), (0, 0, 0))
        ImageDraw.Draw(dummy).text((5, 5), "Test", font=font, fill=(255, 255, 255))
        return font
    except Exception as e:
        print(f"⚠️ Font load failed for {font_path} ({e}), fallback to default")
        try:
            return ImageFont.load_default()
        except:
            return None

# ---------- TEXT PROCESSOR DENGAN HIGHLIGHT ----------
class StableTextProcessor:
    def __init__(self, font, max_width, margin_x=70, margin_right=90):
        self.font = font
        self.max_width = max_width
        self.margin_x = margin_x
        self.margin_right = margin_right
        self.line_height = self._calculate_line_height()

    def _calculate_line_height(self):
        if self.font:
            try:
                bbox = self.font.getbbox("HgypqA")
                lh_text = bbox[3] - bbox[1]
                return max(lh_text + ISILINE_PADDING, 30 + ISILINE_PADDING)
            except:
                return 30 + ISILINE_PADDING
        return 30 + ISILINE_PADDING

    def _get_text_width(self, text):
        if not text:
            return 0
        if self.font:
            try:
                # Prefer getlength if available (accurate with kerning)
                if hasattr(self.font, "getlength"):
                    return self.font.getlength(text)
                # Fallback via textbbox
                dummy = Image.new("RGBA", (1, 1))
                d = ImageDraw.Draw(dummy)
                bbox = d.textbbox((0, 0), text, font=self.font)
                return max(0, bbox[2] - bbox[0])
            except:
                return len(text) * 15
        return len(text) * 15

    def parse_text_with_highlights(self, text):
        try:
            parts = re.split(r'(\[\[.*?\]\])', text)
            segments = []
            for part in parts:
                if not part:
                    continue
                if part.startswith('[[') and part.endswith(']]'):
                    content = part[2:-2].replace('|', ' ')
                    if content:
                        segments.append({'text': content, 'is_highlight': True})
                else:
                    clean = part.replace('|', ' ')
                    if clean:
                        segments.append({'text': clean, 'is_highlight': False})
            return segments
        except Exception as e:
            print(f"⚠️ Parse error: {e}")
            return [{'text': text, 'is_highlight': False}]

    def smart_wrap_with_highlights(self, text):
        """
        Membungkus teks sambil menjaga segmen highlight.
        Menghasilkan list of lines; tiap line berisi list dict {word, is_highlight}.
        """
        segments = self.parse_text_with_highlights(text)
        available_width = self.max_width - self.margin_x - self.margin_right

        # Orphan words ringan untuk konten
        orphan_words = {'di', 'ke', 'rp', 'rupiah', 'juta', 'miliar', 'ribu'}

        def is_orphan(word):
            return word.lower().strip('.,!?;:()[]{}"\'-') in orphan_words

        # Flatten ke daftar kata dengan flag highlight
        words = []
        for seg in segments:
            for w in seg['text'].split():
                words.append({'word': w, 'is_highlight': seg['is_highlight']})

        lines = []
        current = []
        width_acc = 0

        i = 0
        while i < len(words):
            w = words[i]
            w_width = self._get_text_width(w['word'] + " ")

            if width_acc + w_width <= available_width:
                current.append(w)
                width_acc += w_width
                i += 1
            else:
                if current:
                    # Cek orphan terakhir
                    if len(current) > 1 and is_orphan(current[-1]['word']):
                        orphan = current.pop()
                        if current:
                            lines.append(current)
                        current = [orphan]  # mulai baris baru dengan orphan
                        width_acc = self._get_text_width(orphan['word'] + " ")
                    else:
                        lines.append(current)
                        current = []
                        width_acc = 0
                else:
                    # Kata lebih panjang dari lebar tersedia — paksa pindah
                    lines.append([w])
                    i += 1
        if current:
            lines.append(current)

        # Post-fix orphan sederhana antar-baris
        for j in range(len(lines) - 1):
            if len(lines[j]) >= 1 and is_orphan(lines[j][-1]['word']):
                orphan = lines[j].pop()
                lines[j + 1].insert(0, orphan)

        return lines

    def render_lines_with_continuous_highlight(self, lines, base_y, frame_idx, total_frames):
        """
        Highlight progresif lintas-baris:
        - Progres global berbasis total karakter highlight
        - Ease-out di tingkat global dan intra-kata
        """
        try:
            base_img = Image.new("RGBA", VIDEO_SIZE, BG_COLOR + (255,))
            highlight_layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
            text_layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))

            hl_draw = ImageDraw.Draw(highlight_layer)
            txt_draw = ImageDraw.Draw(text_layer)

            # Progres global highlight (lebih cepat = 25% durasi total)
            base_progress = min(1.0, frame_idx / float(max(1, int(total_frames * 0.25))))
            global_progress = 1.0 - pow(1.0 - base_progress, 2.0)  # ease_out quad

            # Kumpulkan segmen highlight dan gambar teks biasa
            segments = []
            total_chars = 0
            y = base_y

            # Offsets untuk kotak highlight
            try:
                bbox_A = self.font.getbbox("A")
                lh_text = bbox_A[3] - bbox_A[1]
            except:
                lh_text = 30
            line_height = max(lh_text + ISILINE_PADDING, 30 + ISILINE_PADDING)
            HIGHLIGHT_TOP_OFFSET = 3 + 6
            HIGHLIGHT_BOTTOM_OFFSET = line_height - 2 + 6

            for line in lines:
                x = self.margin_x
                for wi in line:
                    word = wi['word']
                    width_word = self._get_text_width(word + " ")
                    if wi['is_highlight']:
                        segments.append({
                            'x': x,
                            'y': y,
                            'width': width_word,
                            'word': word,
                            'char_start': total_chars,
                            'char_end': total_chars + len(word)
                        })
                        total_chars += len(word) + 1
                    else:
                        # gambar teks biasa sekarang (boleh digambar ulang nanti)
                        if self.font and word:
                            txt_draw.text((x, y), word + " ", font=self.font, fill=TEXT_COLOR)
                    x += width_word
                y += line_height

            current_chars = int(global_progress * total_chars) if total_chars > 0 else 0

            # Gambar highlight segmen dengan progres halus per-kata
            for seg in segments:
                if seg['char_start'] > current_chars:
                    continue
                chars_into = max(0, current_chars - seg['char_start'])
                word_len = max(1, len(seg['word']))
                if chars_into >= word_len:
                    seg_progress = 1.0
                else:
                    base_p = chars_into / float(word_len)
                    seg_progress = 1.0 - pow(1.0 - base_p, 2.0)  # ease_out intra-kata
                highlight_w = seg['width'] * seg_progress

                hl_draw.rectangle(
                    [
                        seg['x'] - 4,
                        seg['y'] + HIGHLIGHT_TOP_OFFSET,
                        seg['x'] + highlight_w + 4,
                        seg['y'] + HIGHLIGHT_BOTTOM_OFFSET
                    ],
                    fill=HIGHLIGHT_COLOR
                )

            # Render ulang teks highlight agar di atas kotak
            y = base_y
            for line in lines:
                x = self.margin_x
                for wi in line:
                    word = wi['word']
                    width_word = self._get_text_width(word + " ")
                    if self.font and word:
                        txt_draw.text((x, y), word + " ", font=self.font, fill=TEXT_COLOR)
                    x += width_word
                y += line_height

            # Composite
            result = Image.alpha_composite(base_img, highlight_layer)
            result = Image.alpha_composite(result, text_layer)
            return np.array(result.convert("RGB"))
        except Exception as e:
            print(f"⚠️ Render error: {e}")
            return np.zeros((VIDEO_SIZE[1], VIDEO_SIZE[0], 3), dtype=np.uint8)

# ---------- OPENING (WIPE) ----------
def durasi_judul(upper, judul, subjudul):
    panjang = len((upper or "").split()) + len((judul or "").split()) + len((subjudul or "").split())
    if panjang <= 8:
        return 2.5
    elif panjang <= 14:
        return 3.0
    elif panjang <= 22:
        return 3.5
    elif panjang <= 30:
        return 4.0
    return 4.5

def render_opening(upper, judul, subjudul, fonts):
    dur = durasi_judul(upper, judul, subjudul)
    total_frames = int(FPS * dur)
    static_frames = int(FPS * 0.2)
    fade_frames = int(FPS * 0.8)
    margin_x = 70

    font_upper = load_font_safe(fonts["upper"], 28) if upper else None
    font_judul = load_font_safe(fonts["judul"], 54)
    font_sub = load_font_safe(fonts["subjudul"], 28) if subjudul else None

    def smart_wrap(text, font, max_width, margin_left=70, margin_right=90):
        if not text:
            return ""
        paragraphs = text.split("\n")
        out = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                out.append("")
                continue
            line = ""
            for word in para.split():
                test = (line + word + " ")
                if font and hasattr(font, "getlength"):
                    w = font.getlength(test)
                else:
                    dummy = Image.new("RGBA", (1, 1))
                    d = ImageDraw.Draw(dummy)
                    bbox = d.textbbox((0, 0), test, font=font)
                    w = bbox[2] - bbox[0]
                if w + margin_left + margin_right > max_width:
                    out.append(line.strip())
                    line = word + " "
                else:
                    line = test
            if line:
                out.append(line.strip())
        return "\n".join(out)

    wrapped_upper = smart_wrap(upper, font_upper, VIDEO_SIZE[0]) if upper and font_upper else ""
    wrapped_judul = smart_wrap(judul, font_judul, VIDEO_SIZE[0]) if judul and font_judul else ""
    wrapped_sub = smart_wrap(subjudul, font_sub, VIDEO_SIZE[0]) if subjudul and font_sub else ""

    base_y = int(VIDEO_SIZE[1] * 0.60)
    y_upper = None
    y_judul = base_y
    if wrapped_upper and font_upper:
        try:
            upper_h = sum((font_upper.getbbox(line)[3] - font_upper.getbbox(line)[1]) for line in wrapped_upper.split("\n") if line.strip())
            y_upper = base_y - upper_h - 20
        except:
            y_upper = base_y - 50
    if wrapped_sub and font_judul:
        try:
            judul_h = sum((font_judul.getbbox(line)[3] - font_judul.getbbox(line)[1]) for line in wrapped_judul.split("\n") if line.strip())
            y_sub = y_judul + judul_h + 25
        except:
            y_sub = y_judul + 80
    else:
        y_sub = None

    def make_frame(t):
        i = int(t * FPS)
        if i < static_frames:
            prog = 1.0
            anim = False
        elif i < static_frames + fade_frames:
            prog = (i - static_frames) / float(fade_frames)
            anim = True
        else:
            prog = 1.0
            anim = False

        frame = Image.new("RGBA", VIDEO_SIZE, BG_COLOR + (255,))
        layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        if wrapped_upper and font_upper and y_upper is not None:
            draw.multiline_text((margin_x, y_upper), wrapped_upper, font=font_upper, fill=TEXT_COLOR, align="left")
        if wrapped_judul and font_judul:
            draw.multiline_text((margin_x, y_judul), wrapped_judul, font=font_judul, fill=TEXT_COLOR, align="left")
        if wrapped_sub and font_sub and y_sub is not None:
            draw.multiline_text((margin_x, y_sub), wrapped_sub, font=font_sub, fill=TEXT_COLOR, align="left")

        if anim and prog < 1.0:
            t_eased = 1.0 - pow(1.0 - prog, 3.0)
            width = int(VIDEO_SIZE[0] * t_eased)
            mask = Image.new("L", VIDEO_SIZE, 0)
            ImageDraw.Draw(mask).rectangle([0, 0, width, VIDEO_SIZE[1]], fill=255)
            visible = Image.composite(layer, Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0)), mask)
        else:
            visible = layer

        composed = Image.alpha_composite(frame, visible)
        return np.array(composed.convert("RGB"))

    return VideoClip(make_frame, duration=dur)

# ---------- KONTEN ISI: MULTILINE HIGHLIGHT + WIPE ----------
def render_text_block(text, font_path, font_size, dur):
    total_frames = int(FPS * dur)
    wipe_frames = min(int(FPS * 0.8), total_frames)  # 0.8s wipe
    margin_x = 70
    base_y = int(VIDEO_SIZE[1] * 0.60)
    margin_bawah_logo = 170
    batas_bawah_aman = VIDEO_SIZE[1] - margin_bawah_logo

    font = load_font_safe(font_path, font_size)
    if not font:
        font = load_font_safe(font_path, 24)

    processor = StableTextProcessor(font, VIDEO_SIZE[0], margin_x=margin_x, margin_right=90)
    wrapped_lines = processor.smart_wrap_with_highlights(text)

    # Hitung tinggi total untuk pengecekan batas bawah
    total_h = len(wrapped_lines) * processor.line_height
    bottom_y = base_y + total_h
    if bottom_y > batas_bawah_aman:
        overflow = bottom_y - batas_bawah_aman
        base_y = max(80, base_y - min(overflow + 40, 250))

    def make_frame(t):
        i = int(t * FPS)
        # Render dasar (highlight + text)
        base_frame = processor.render_lines_with_continuous_highlight(wrapped_lines, base_y, i, total_frames)

        # Terapkan wipe di awal
        if i < wipe_frames:
            prog = i / float(max(1, wipe_frames))
            t_eased = 1.0 - pow(1.0 - prog, 3.0)
            wipe_w = int(VIDEO_SIZE[0] * t_eased)

            frame_img = Image.fromarray(base_frame)
            mask = Image.new("L", VIDEO_SIZE, 0)
            ImageDraw.Draw(mask).rectangle([0, 0, wipe_w, VIDEO_SIZE[1]], fill=255)

            black_bg = Image.new("RGB", VIDEO_SIZE, BG_COLOR)
            frame = Image.composite(frame_img, black_bg, mask)
            return np.array(frame)
        else:
            return base_frame

    return VideoClip(make_frame, duration=dur)

# ---------- SEPARATOR / PENUTUP ----------
def render_separator(dur=0.7):
    frame = np.zeros((VIDEO_SIZE[1], VIDEO_SIZE[0], 3), dtype=np.uint8)
    return ImageClip(frame, duration=dur)

# ---------- OVERLAY ----------
def add_overlay(base_clip):
    if not os.path.exists(OVERLAY_FILE):
        print(f"⚠️ Overlay file {OVERLAY_FILE} not found, skipping overlay")
        return base_clip
    try:
        img = Image.open(OVERLAY_FILE).convert("RGBA").resize(VIDEO_SIZE, Image.LANCZOS)
        overlay = ImageClip(np.array(img), duration=base_clip.duration)
        return CompositeVideoClip([base_clip, overlay.set_pos((0, 0))], size=VIDEO_SIZE)
    except Exception as e:
        print(f"❌ Failed to apply overlay: {e}")
        return base_clip

# ---------- PARSER DATA STABIL ----------
def baca_semua_berita_stable(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()

        all_data = []
        current = {}
        isi_counter = 1
        state = None

        for raw in content.split('\n'):
            line = raw.strip()
            if not line:
                continue
            if line.lower().startswith('upper:'):
                if current and (any(k.startswith('Isi_') for k in current.keys()) or 'Judul' in current or 'Subjudul' in current):
                    all_data.append(current)
                current = {}
                isi_counter = 1
                state = 'upper'
                current['Upper'] = line.split(':', 1)[1].strip()
            elif line.lower().startswith('judul:'):
                state = 'judul'
                current['Judul'] = line.split(':', 1)[1].strip()
            elif line.lower().startswith('subjudul:'):
                state = 'subjudul'
                current['Subjudul'] = line.split(':', 1)[1].strip()
            else:
                if state == 'upper':
                    current['Upper'] = (current.get('Upper', '') + ('\n' if current.get('Upper') else '') + line).strip()
                elif state == 'judul':
                    if len(line) > 100 or '[[' in line:
                        state = 'isi'
                        current[f'Isi_{isi_counter}'] = line
                        isi_counter += 1
                    else:
                        current['Judul'] = (current.get('Judul', '') + ('\n' if current.get('Judul') else '') + line).strip()
                elif state == 'subjudul':
                    if len(line) > 100 or '[[' in line:
                        state = 'isi'
                        current[f'Isi_{isi_counter}'] = line
                        isi_counter += 1
                    else:
                        current['Subjudul'] = (current.get('Subjudul', '') + ('\n' if current.get('Subjudul') else '') + line).strip()
                else:
                    state = 'isi'
                    current[f'Isi_{isi_counter}'] = line
                    isi_counter += 1

        if current and (any(k.startswith('Isi_') for k in current.keys()) or 'Judul' in current or 'Subjudul' in current or 'Upper' in current):
            all_data.append(current)

        print(f"📊 Parsed {len(all_data)} data entries")
        return all_data
    except Exception as e:
        print(f"❌ Parse failed: {e}")
        return []

# ---------- DURASI CERDAS ----------
def hitung_durasi_isi(text):
    try:
        if not text:
            return 3.0
        clean = re.sub(r'\[\[.*?\]\]', lambda m: m.group(0)[2:-2], text).replace('\n', ' ').strip()
        kata = len(clean.split())
        dur = (kata / 160.0) * 60.0  # 160 WPM
        if len(clean) > 300:
            dur *= 1.4
        elif len(clean) > 200:
            dur *= 1.2
        dur = max(3.0, min(10.0, dur))
        dur += 1.5
        return round(dur, 1)
    except:
        return 5.0

# ---------- PIPELINE ----------
def buat_video_stable(data, i=None):
    try:
        print(f"\n🎬 STARTING VIDEO {i+1 if i is not None else 1}")
        print("=" * 60)
        print(f"📝 Title: {data.get('Judul', 'No Title')}")

        opening = render_opening(
            data.get("Upper", ""), 
            data.get("Judul", ""), 
            data.get("Subjudul", ""), 
            FONTS
        )

        isi_keys = sorted([k for k in data.keys() if k.startswith("Isi_")], key=lambda x: int(x.split('_')[-1]))
        clips = []
        sep = render_separator(0.7)

        if isi_keys:
            for idx, k in enumerate(isi_keys, 1):
                teks = data[k]
                dur = hitung_durasi_isi(teks)
                print(f"   {k}: {len(teks)} chars → {dur}s")
                clips.append(render_text_block(teks, FONTS["isi"], 34, dur))
                if idx < len(isi_keys):
                    clips.append(sep)
        else:
            clips.append(render_text_block("Konten tidak tersedia", FONTS["isi"], 34, 3.0))

        ending = render_separator(3.0)
        final = concatenate_videoclips([opening, sep] + clips + [ending], method="compose")
        result = add_overlay(final)

        fname = f"output_video_multiline_{(i or 0)+1}.mp4"
        print(f"🎥 Encoding: {fname}")
        result.write_videofile(
            fname,
            fps=FPS,
            codec="libx264",
            audio=False,
            preset="medium",
            logger=None,
            threads=4
        )
        print(f"✅ Done: {fname}")
    except Exception as e:
        print(f"❌ VIDEO FAILED: {e}")
        traceback.print_exc()

# ---------- MAIN ----------
if __name__ == "__main__":
    print("🚀 MULTILINE HIGHLIGHT VIDEO GENERATOR")
    FILE_INPUT = "data_berita.txt"
    if not os.path.exists(FILE_INPUT):
        print("❌ File data_berita.txt tidak ditemukan.")
        sys.exit(1)

    # Cek font agar tidak langsung gagal
    missing = []
    for k, f in FONTS.items():
        if not os.path.exists(f):
            missing.append(f)
    if missing:
        print("⚠️ Font berikut tidak ditemukan (akan fallback ke default):")
        for m in missing:
            print(f"   - {m}")

    data_all = baca_semua_berita_stable(FILE_INPUT)
    if not data_all:
        print("❌ No data to process")
        sys.exit(1)

    print(f"\n🎬 Processing {len(data_all)} videos...")
    for i, d in enumerate(data_all):
        buat_video_stable(d, i)

    print("\n🎉 ALL VIDEOS COMPLETED!")
