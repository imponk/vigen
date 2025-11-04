# ==========================================================
# ✅ VIDEO GENERATOR - MULTILINE SMOOTH HIGHLIGHT (V2, layout meniru versi awal)
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
# PERUBAHAN 1: BG_COLOR diubah ke Abu-abu Netral (128, 128, 128)
BG_COLOR = (128, 128, 128) 
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
HIGHLIGHT_SPEED_FRAC = 0.35  # Bagian durasi untuk sweep highlight (lebih smooth dari 0.25)


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


def ease_out_cubic(t):
    return 1.0 - pow(1.0 - t, 3.0)


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

    def _measure_text(self, text):
        if not text:
            return 0
        if self.font:
            try:
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
            w_width = self._measure_text(w['word'] + " ")

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
                        width_acc = self._measure_text(orphan['word'] + " ")
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
        - Ease-out global cubic dan intra-kata
        - Mengukur lebar substring per-frame untuk transisi benar-benar halus
        """
        try:
            base_img = Image.new("RGBA", VIDEO_SIZE, BG_COLOR + (255,)) 
            highlight_layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
            text_layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))

            hl_draw = ImageDraw.Draw(highlight_layer)
            txt_draw = ImageDraw.Draw(text_layer)

            # Progres global highlight (lebih halus = 35% durasi total)
            span_frames = max(1, int(total_frames * HIGHLIGHT_SPEED_FRAC))
            base_progress = min(1.0, frame_idx / float(span_frames))
            global_progress = ease_out_cubic(base_progress)

            # Kumpulkan segmen highlight
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

            # Pre-render: ukur semua kata untuk posisi x
            positions_per_line = []
            for line in lines:
                x = self.margin_x
                pos_line = []
                for wi in line:
                    word = wi['word']
                    width_word = self._measure_text(word + " ")
                    pos_line.append((x, wi, width_word))
                    x += width_word
                positions_per_line.append((y, pos_line))
                y += line_height

            # Hitung total_chars dari hanya segmen highlight
            for y_line, pos_line in positions_per_line:
                for (x, wi, width_word) in pos_line:
                    if wi['is_highlight']:
                        segments.append({
                            'x': x,
                            'y': y_line,
                            'width': width_word,
                            'word': wi['word'],
                            'char_start': total_chars,
                            'char_end': total_chars + len(wi['word'])
                        })
                        total_chars += len(wi['word']) + 1  # + spasi

            current_chars = int(global_progress * total_chars) if total_chars > 0 else 0

            # Gambar highlight segmen dengan progres halus berbasis lebar substring aktual
            for seg in segments:
                if seg['char_start'] > current_chars:
                    continue

                chars_into = max(0, current_chars - seg['char_start'])
                word_len = max(1, len(seg['word']))
                chars_into = min(chars_into, word_len)

                if chars_into >= word_len:
                    highlight_w = seg['width']
                else:
                    # Ukur lebar substring aktual untuk transisi super halus (proporsional huruf)
                    partial_text = seg['word'][:chars_into]
                    # smooth intra-kata dengan cubic easing terhadap 1 char berikutnya
                    intra = 0.0
                    if chars_into < word_len:
                        # fraksi menuju karakter berikutnya untuk sedikit interpolasi subpixel
                        # gunakan sisa progres global kecil untuk smoothing mikro
                        frac = (global_progress * total_chars - seg['char_start'] - chars_into)
                        frac = max(0.0, min(1.0, frac))
                        intra = ease_out_cubic(frac)
                    partial_plus = partial_text
                    # Hitung lebar substring
                    base_w = self._measure_text(partial_plus)
                    next_char_w = 0
                    if chars_into < word_len:
                        next_char_w = self._measure_text(seg['word'][:chars_into+1]) - base_w
                    highlight_w = base_w + intra * next_char_w

                hl_draw.rectangle(
                    [
                        seg['x'] - 4,
                        seg['y'] + HIGHLIGHT_TOP_OFFSET,
                        seg['x'] + highlight_w - 4,
                        seg['y'] + HIGHLIGHT_BOTTOM_OFFSET
                    ],
                    fill=HIGHLIGHT_COLOR
                )

            # Gambar teks di atas highlight (seluruh teks)
            for y_line, pos_line in positions_per_line:
                for (x, wi, width_word) in pos_line:
                    word = wi['word']
                    if self.font and word:
                        txt_draw.text((x, y_line), word + " ", font=self.font, fill=TEXT_COLOR)

            # Composite
            result = Image.alpha_composite(base_img, highlight_layer)
            result = Image.alpha_composite(result, text_layer)
            return np.array(result.convert("RGB"))
        except Exception as e:
            print(f"⚠️ Render error: {e}")
            return np.zeros((VIDEO_SIZE[1], VIDEO_SIZE[0], 3), dtype=np.uint8)


# ---------- OPENING (LAYOUT MENIRU VERSI AWAL) ----------
def durasi_judul_awal(upper, judul, subjudul):
    panjang = len((upper or "").split()) + len((judul or "").split()) + len((subjudul or "").split())
    if panjang <= 8: return 2.5
    elif panjang <= 14: return 3.0
    elif panjang <= 22: return 3.5
    return 4.0


def render_opening(upper_txt, judul_txt, subjudul_txt, fonts):
    dur = durasi_judul_awal(upper_txt, judul_txt, subjudul_txt)
    total_frames = int(FPS * dur)
    static_frames = int(FPS * 0.2)
    fade_frames = int(FPS * 0.8)
    margin_x = 70
    margin_bawah_logo = 170
    batas_bawah_aman = VIDEO_SIZE[1] - margin_bawah_logo

    dummy_img = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy_img)
    upper_font_size = 28
    judul_font_size = 60
    sub_font_size = 28
    
    # PERUBAHAN 2: Penyesuaian jarak vertikal (Upper <-> Judul <-> Subjudul)
    spacing_upper_judul = 8    # Diubah dari 12 menjadi 8
    spacing_judul_sub = 12     # Diubah dari 19 menjadi 12

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
                try:
                    bbox = draw.textbbox((0, 0), test, font=font)
                    w = bbox[2] - bbox[0]
                except:
                    w = len(test) * 15
                if w + margin_left + margin_right > max_width:
                    out.append(line.strip())
                    line = word + " "
                else:
                    line = test
            if line:
                out.append(line.strip())
        return "\n".join(out)

    def calculate_layout(current_judul_font_size):
        font_upper = ImageFont.truetype(fonts["upper"], upper_font_size) if (upper_txt and os.path.exists(fonts["upper"])) else load_font_safe(fonts["upper"], upper_font_size) if upper_txt else None
        font_judul = ImageFont.truetype(fonts["judul"], current_judul_font_size) if (judul_txt and os.path.exists(fonts["judul"])) else load_font_safe(fonts["judul"], current_judul_font_size) if judul_txt else None
        font_sub = ImageFont.truetype(fonts["subjudul"], sub_font_size) if (subjudul_txt and os.path.exists(fonts["subjudul"])) else load_font_safe(fonts["subjudul"], sub_font_size) if subjudul_txt else None

        wrapped_upper = smart_wrap(upper_txt, font_upper, VIDEO_SIZE[0]) if font_upper and upper_txt else None
        wrapped_judul = smart_wrap(judul_txt, font_judul, VIDEO_SIZE[0]) if font_judul and judul_txt else ""
        wrapped_sub = smart_wrap(subjudul_txt, font_sub, VIDEO_SIZE[0]) if font_sub and subjudul_txt else None

        y_start = int(VIDEO_SIZE[1] * 0.60)
        current_y = y_start
        y_upper = y_judul = y_sub = None
        bottom_y = y_start

        if wrapped_upper:
            y_upper = current_y
            upper_bbox = draw.multiline_textbbox((margin_x, y_upper), wrapped_upper, font=font_upper, spacing=4)
            current_y = upper_bbox[3] + spacing_upper_judul
            bottom_y = upper_bbox[3]

        y_judul = current_y
        if wrapped_judul:
            judul_bbox = draw.multiline_textbbox((margin_x, y_judul), wrapped_judul, font=font_judul, spacing=4)
            bottom_y = judul_bbox[3]
            current_y = judul_bbox[3] + spacing_judul_sub

        if wrapped_sub:
            y_sub = current_y
            sub_bbox = draw.multiline_textbbox((margin_x, y_sub), wrapped_sub, font=font_sub, spacing=4)
            bottom_y = sub_bbox[3]

        return {
            "font_upper": font_upper, "font_judul": font_judul, "font_sub": font_sub,
            "wrapped_upper": wrapped_upper if wrapped_upper else None,
            "wrapped_judul": wrapped_judul,
            "wrapped_sub": wrapped_sub if wrapped_sub else None,
            "y_upper": y_upper, "y_judul": y_judul, "y_sub": y_sub, "bottom_y": bottom_y
        }

    layout = calculate_layout(judul_font_size)
    if layout["bottom_y"] > batas_bawah_aman:
        layout = calculate_layout(int(judul_font_size * 0.94))

    # Jika masih terlalu rendah, geser ke atas (meniru patch versi awal)
    if layout["bottom_y"] > batas_bawah_aman:
        kelebihan = layout["bottom_y"] - batas_bawah_aman
        offset = min(kelebihan + 20, 150)
        for key in ["y_upper", "y_judul", "y_sub"]:
            if layout[key] is not None:
                layout[key] -= offset

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
        if layout["wrapped_upper"] and layout["y_upper"] is not None:
            ImageDraw.Draw(layer).multiline_text((margin_x, layout["y_upper"]), layout["wrapped_upper"], font=layout["font_upper"], fill=TEXT_COLOR, align="left", spacing=4)
        if layout["wrapped_judul"] and layout["y_judul"] is not None:
            ImageDraw.Draw(layer).multiline_text((margin_x, layout["y_judul"]), layout["wrapped_judul"], font=layout["font_judul"], fill=TEXT_COLOR, align="left", spacing=4)
        if layout["wrapped_sub"] and layout["y_sub"] is not None:
            ImageDraw.Draw(layer).multiline_text((margin_x, layout["y_sub"]), layout["wrapped_sub"], font=layout["font_sub"], fill=TEXT_COLOR, align="left", spacing=4)

        if anim and prog < 1.0:
            t_eased = ease_out_cubic(prog)
            width = int(VIDEO_SIZE[0] * t_eased)
            mask = Image.new("L", VIDEO_SIZE, 0)
            ImageDraw.Draw(mask).rectangle([0, 0, width, VIDEO_SIZE[1]], fill=255)
            visible = Image.composite(layer, Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0)), mask)
        else:
            visible = layer

        composed = Image.alpha_composite(frame, visible)
        return np.array(composed.convert("RGB"))

    return VideoClip(make_frame, duration=dur)


# ---------- KONTEN ISI: MULTILINE HIGHLIGHT + WIPE (LAYOUT MENIRU AWAL) ----------
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

    # Wrap teks isi meniru versi awal (smart_wrap dengan placeholder aman tidak diperlukan di sini,
    # karena processor sudah memelihara highlight via tokenisasi)
    processor = StableTextProcessor(font, VIDEO_SIZE[0], margin_x=margin_x, margin_right=90)
    wrapped_lines = processor.smart_wrap_with_highlights(text)

    # Hitung tinggi total seperti versi awal (pakai line height + ISILINE_PADDING-2 untuk bbox)
    total_h = len(wrapped_lines) * processor.line_height
    # Batas bawah aman
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
            t_eased = ease_out_cubic(prog)
            wipe_w = int(VIDEO_SIZE[0] * t_eased)

            frame_img = Image.fromarray(base_frame)
            mask = Image.new("L", VIDEO_SIZE, 0)
            ImageDraw.Draw(mask).rectangle([0, 0, wipe_w, VIDEO_SIZE[1]], fill=255)

            # Transisi wipe menggunakan BG_COLOR yang baru.
            colored_bg = Image.new("RGB", VIDEO_SIZE, BG_COLOR) 
            frame = Image.composite(frame_img, colored_bg, mask)
            return np.array(frame)
        else:
            return base_frame

    return VideoClip(make_frame, duration=dur)


# ---------- SEPARATOR / PENUTUP ----------
def render_separator(dur=0.7):
    # Frame separator menggunakan BG_COLOR yang baru.
    frame = np.full((VIDEO_SIZE[1], VIDEO_SIZE[0], 3), BG_COLOR, dtype=np.uint8) 
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

        fname = f"output_video_multiline_v2_{(i or 0)+1}.mp4"
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
    print("🚀 MULTILINE HIGHLIGHT VIDEO GENERATOR (V2)")
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
