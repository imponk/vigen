from moviepy.editor import ImageClip, CompositeVideoClip, concatenate_videoclips
from moviepy.video.VideoClip import VideoClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np, os, math, re

# Konfigurasi dasar
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

# 🔥 Tambahan Konfigurasi Highlight (MINIMAL)
HIGHLIGHT_COLOR = (0, 124, 188, 255) # Warna biru muda
HIGHLIGHT_SPEED = 2.0 # Kecepatan swipe dalam detik
ISILINE_PADDING = 5 # Jarak vertikal antar baris

# ===============================
#   DURASI & TEKS PEMBANTU
# ===============================

def durasi_otomatis(teks, min_dur=3.5):
    if not teks:
        return min_dur
    # 🔥 Modifikasi 1/3: Bersihkan markup highlight untuk hitungan kata
    cleaned_text = re.sub(r'\[\[.*?\]\]', lambda m: m.group(0)[2:-2], teks)
    kata = len(cleaned_text.split())
    if kata <= 15:
        durasi = 4
    elif kata <= 30:
        durasi = 5.5
    elif kata <= 50:
        durasi = 7
    else:
        durasi = 8
    return max(min_dur, round(durasi, 1))

def durasi_judul(judul, subjudul):
    panjang = len((judul or "").split()) + len((subjudul or "").split())
    if panjang <= 8: return 2.5
    elif panjang <= 14: return 3.0
    elif panjang <= 22: return 3.5
    return 4.0

def smart_wrap(text, font, max_width, margin_left=70, margin_right=90):
    """
    🔥 Modifikasi 2/3: Menambahkan perlindungan markup [[...]] agar tidak terpotong
    dan dapat di-render oleh fungsi highlight.
    """
    if not text: return ""
    paragraphs = text.split("\n")
    raw_lines = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            raw_lines.append("")
            continue
            
        # 🔥 V61 FIX: Lindungi markup highlight dari pemotongan wrap dengan placeholder '|'
        protected_para = re.sub(r'(\[\[.*?\]\])', lambda m: m.group(1).replace(' ', '|'), para)
        words = protected_para.split()
        line = ""
        for word in words:
            test_line = line + word + " "
            try:
                # Gunakan teks yang sudah dibersihkan dari placeholder '|' untuk menghitung lebar
                dummy_img = Image.new("RGBA", (1, 1))
                draw = ImageDraw.Draw(dummy_img)
                bbox = draw.textbbox((0, 0), test_line.replace('|', ' '), font=font)
                test_width = bbox[2] - bbox[0]
            except Exception: # Fallback jika font.getbbox bermasalah
                test_width = 1000 
                
            if test_width + margin_left + margin_right > max_width:
                raw_lines.append(line.strip())
                line = word + " "
            else:
                line = test_line
        if line: raw_lines.append(line.strip())

    cleaned_lines = []
    for i in range(len(raw_lines)):
        current_line = raw_lines[i]
        
        # Kembalikan placeholder '|' menjadi ' ' untuk proses pemotongan terakhir
        current_line = current_line.replace('|', ' ')
        
        if i == len(raw_lines) - 1:
            cleaned_lines.append(current_line)
            break
        current_line_words = current_line.split()
        if not current_line_words:
            cleaned_lines.append(current_line)
            continue
            
        last_word = current_line_words[-1]
        
        if last_word.lower() in ['rp', 'ke', 'di']:
            line_without_last_word = " ".join(current_line_words[:-1])
            cleaned_lines.append(line_without_last_word)
            if i + 1 < len(raw_lines):
                # NOTE: Kata yang dipindah harus dilindungi kembali agar tidak diubah oleh .replace('|',' ') di baris berikutnya
                word_to_move = re.sub(r'(\[\[.*?\]\])', lambda m: m.group(1).replace(' ', '|'), last_word)
                raw_lines[i+1] = word_to_move + " " + raw_lines[i+1]
        else:
            cleaned_lines.append(current_line)
            
    return "\n".join(cleaned_lines)


# ===============================
#   UTILITAS FRAME
# ===============================

def make_text_frame(base_img, text, font, pos, alpha=255):
    draw = ImageDraw.Draw(base_img)
    fill = (TEXT_COLOR[0], TEXT_COLOR[1], TEXT_COLOR[2], alpha)
    # FIX: Ganti spacing=4 dengan ISILINE_PADDING-1 agar konsisten dengan highlight
    draw.multiline_text(pos, text, font=font, fill=fill, align="left", spacing=4)

# 🔥 Tambahkan Fungsi Highlight Baru (Minimal Perubahan)
def make_text_and_highlight_frame(font,text,pos,frame_idx,total_frames):
    """
    Fungsi baru untuk render teks isi dengan highlight geser (Termasuk Perbaikan V61).
    """
    margin_x,y=pos
    hl=Image.new("RGBA",VIDEO_SIZE,(0,0,0,0))
    tx=Image.new("RGBA",VIDEO_SIZE,(0,0,0,0))
    dhl,dt=ImageDraw.Draw(hl),ImageDraw.Draw(tx)
    
    # Hitung tinggi baris (lh)
    try: 
        lh_text = max(font.getbbox("A")[3] - font.getbbox("A")[1], font.getsize("A")[1])
        lh = lh_text + ISILINE_PADDING 
    except: 
        lh = 30 + ISILINE_PADDING
    
    # 🔥 V61 FIX: Geser kotak highlight ke bawah 6 piksel
    HIGHLIGHT_TOP_OFFSET = 3 + 6      # Posisi Y atas kotak
    HIGHLIGHT_BOTTOM_OFFSET = lh - 2 + 6 # Posisi Y bawah kotak

    swipe=int(FPS*HIGHLIGHT_SPEED)
    for line in text.split("\n"):
        parts=re.split(r"(\[\[.*?\]\])",line)
        cx=margin_x
        for p in parts:
            if not p: continue
            if p.startswith("[[") and p.endswith("]]"):
                # Bagian yang di-highlight
                w=p[2:-2].replace('|', ' ') # Kembalikan placeholder '|' menjadi ' '
                
                try: 
                    dummy_img = Image.new("RGBA", (1, 1))
                    draw = ImageDraw.Draw(dummy_img)
                    bbox = draw.textbbox((0, 0), w, font=font)
                    ww = bbox[2] - bbox[0]
                except: ww=len(w)*20
                
                prog=min(1.0,frame_idx/float(swipe)); xs=cx+ww*(1-prog)
                
                # Render kotak highlight
                dhl.rectangle([
                    xs-4, 
                    y + HIGHLIGHT_TOP_OFFSET, 
                    cx+ww+4, 
                    y + HIGHLIGHT_BOTTOM_OFFSET
                ],fill=HIGHLIGHT_COLOR)
                
                dt.text((cx,y),w,font=font,fill=TEXT_COLOR); cx+=ww+4
            else:
                # Bagian teks biasa
                p_clean = p.replace('|', ' ')
                try: 
                    dummy_img = Image.new("RGBA", (1, 1))
                    draw = ImageDraw.Draw(dummy_img)
                    bbox = draw.textbbox((0, 0), p_clean, font=font)
                    width_text = bbox[2] - bbox[0]
                    dt.text((cx,y),p_clean,font=font,fill=TEXT_COLOR); cx+=width_text
                except: 
                    dt.text((cx,y),p_clean,font=font,fill=TEXT_COLOR); cx+=len(p_clean)*20
        y+=lh
    return hl,tx

def ease_out(t):  
    return 1 - pow(1 - t, 3)

def render_wipe_layer(layer, t):
    if t <= 0: return Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
    t_eased = ease_out(t)
    width = int(VIDEO_SIZE[0] * t_eased)
    mask = Image.new("L", VIDEO_SIZE, 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle([0, 0, width, VIDEO_SIZE[1]], fill=255)
    return Image.composite(layer, Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0)), mask)

# ===============================
#   STREAMING RENDER CLIPS
# ===============================

def make_clip_from_generator(frame_generator, duration):
# ... (Fungsi ini tetap sama) ...
    def make_frame(t):
        i = int(t * FPS)
        return frame_generator(i)
    return VideoClip(make_frame, duration=duration)

def render_opening(judul_txt, subjudul_txt, fonts, upper_txt=None):
# ... (Fungsi ini tetap sama) ...
    dur = durasi_judul(judul_txt, subjudul_txt)
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
    spacing_upper_judul = 12
    spacing_judul_sub = 19

    def calculate_layout(current_judul_font_size):
        font_upper = ImageFont.truetype(fonts["upper"], upper_font_size) if upper_txt else None
        font_judul = ImageFont.truetype(fonts["judul"], current_judul_font_size) if judul_txt else None
        font_sub = ImageFont.truetype(fonts["subjudul"], sub_font_size) if subjudul_txt else None
        if not font_judul:
            font_judul = ImageFont.truetype(fonts["judul"], current_judul_font_size)

        wrapped_upper = smart_wrap(upper_txt, font_upper, VIDEO_SIZE[0]) if font_upper and upper_txt else None
        wrapped_judul = smart_wrap(judul_txt, font_judul, VIDEO_SIZE[0]) if font_judul and judul_txt else ""
        wrapped_sub = smart_wrap(subjudul_txt, font_sub, VIDEO_SIZE[0]) if font_sub and subjudul_txt else None

        upper_h = judul_h = sub_h = 0
        if wrapped_upper:
            # FIX: replace('|', ' ') untuk memastikan perhitungan layout yang akurat
            upper_bbox = draw.multiline_textbbox((0, 0), wrapped_upper.replace('|', ' '), font=font_upper, spacing=4)
            upper_h = upper_bbox[3] - upper_bbox[1]
        if wrapped_judul:
            judul_bbox = draw.multiline_textbbox((0, 0), wrapped_judul.replace('|', ' '), font=font_judul, spacing=4)
            judul_h = judul_bbox[3] - judul_bbox[1]
        if wrapped_sub:
            sub_bbox = draw.multiline_textbbox((0, 0), wrapped_sub.replace('|', ' '), font=font_sub, spacing=4)
            sub_h = sub_bbox[3] - sub_bbox[1]

        y_start = int(VIDEO_SIZE[1] * 0.60)
        current_y = y_start
        y_upper = y_judul = y_sub = None
        bottom_y = y_start

        if wrapped_upper:
            y_upper = current_y
            upper_bbox = draw.multiline_textbbox((margin_x, y_upper), wrapped_upper.replace('|', ' '), font=font_upper, spacing=4)
            current_y = upper_bbox[3] + spacing_upper_judul
            bottom_y = upper_bbox[3]

        y_judul = current_y
        if wrapped_judul:
            judul_bbox = draw.multiline_textbbox((margin_x, y_judul), wrapped_judul.replace('|', ' '), font=font_judul, spacing=4)
            bottom_y = judul_bbox[3]
            current_y = judul_bbox[3] + spacing_judul_sub

        if wrapped_sub:
            y_sub = current_y
            sub_bbox = draw.multiline_textbbox((margin_x, y_sub), wrapped_sub.replace('|', ' '), font=font_sub, spacing=4)
            bottom_y = sub_bbox[3]

        return {
            "font_upper": font_upper, "font_judul": font_judul, "font_sub": font_sub,
            "wrapped_upper": wrapped_upper.replace('|', ' ') if wrapped_upper else None, # Ganti kembali placeholder
            "wrapped_judul": wrapped_judul.replace('|', ' '), 
            "wrapped_sub": wrapped_sub.replace('|', ' ') if wrapped_sub else None, # Ganti kembali placeholder
            "y_upper": y_upper, "y_judul": y_judul, "y_sub": y_sub, "bottom_y": bottom_y
        }

    layout = calculate_layout(judul_font_size)
    if layout["bottom_y"] > batas_bawah_aman:
        layout = calculate_layout(int(judul_font_size * 0.94))

    # 🔧 Tambahan patch: jika masih terlalu rendah, geser ke atas
    if layout["bottom_y"] > batas_bawah_aman:
        kelebihan = layout["bottom_y"] - batas_bawah_aman
        offset = min(kelebihan + 20, 150)
        for key in ["y_upper", "y_judul", "y_sub"]:
            if layout[key] is not None:
                layout[key] -= offset

    def frame_generator(i):
        if i < static_frames:
            t = 1.0
            anim = False
        elif i < static_frames + fade_frames:
            t = (i - static_frames) / float(fade_frames)
            anim = True
        else:
            t = 1.0
            anim = False

        frame = Image.new("RGBA", VIDEO_SIZE, BG_COLOR + (255,))
        layer = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
        if layout["wrapped_upper"] and layout["y_upper"] is not None:
            make_text_frame(layer, layout["wrapped_upper"], layout["font_upper"], (margin_x, layout["y_upper"]))
        if layout["wrapped_judul"] and layout["y_judul"] is not None:
            make_text_frame(layer, layout["wrapped_judul"], layout["font_judul"], (margin_x, layout["y_judul"]))
        if layout["wrapped_sub"] and layout["y_sub"] is not None:
            make_text_frame(layer, layout["wrapped_sub"], layout["font_sub"], (margin_x, layout["y_sub"]))
        visible = render_wipe_layer(layer, t) if anim else layer
        return np.array(Image.alpha_composite(frame, visible).convert("RGB"))

    return make_clip_from_generator(frame_generator, dur)

def render_text_block(text, font_path, font_size, dur, anim=True):
    total_frames = int(FPS * dur)
    fade_frames = min(18, total_frames)
    margin_x = 70
    base_y = int(VIDEO_SIZE[1] * 0.60)
    margin_bawah_logo = 170
    batas_bawah_aman = VIDEO_SIZE[1] - margin_bawah_logo

    dummy_img = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy_img)
    font = ImageFont.truetype(font_path, font_size)
    wrapped = smart_wrap(text, font, VIDEO_SIZE[0])
    
    # 🔥 Modifikasi 3/3: Menggunakan ISILINE_PADDING-2 dan .replace('|', ' ')
    text_bbox = draw.multiline_textbbox((0, 0), wrapped.replace('|', ' '), font=font, spacing=ISILINE_PADDING-2)
    text_height = text_bbox[3] - text_bbox[1]
    bottom_y = base_y + text_height
    if bottom_y > batas_bawah_aman:
        font_size_new = max(30, int(font_size * 0.94))
        font = ImageFont.truetype(font_path, font_size_new)
        wrapped = smart_wrap(text, font, VIDEO_SIZE[0])
        # FIX: Menggunakan ISILINE_PADDING-2 dan .replace('|', ' ')
        text_bbox = draw.multiline_textbbox((0, 0), wrapped.replace('|', ' '), font=font, spacing=ISILINE_PADDING-2)
        text_height = text_bbox[3] - text_bbox[1]
        bottom_y = base_y + text_height
    y_pos = base_y if bottom_y <= batas_bawah_aman else base_y - min(bottom_y - batas_bawah_aman + 10, 220)

    def frame_generator(i):
        t = 1.0 if not anim else min(1.0, i / float(fade_frames))
        frame = Image.new("RGBA", VIDEO_SIZE, BG_COLOR + (255,))
        
        # 🔥 GANTI LOGIKA LAMA: Menggunakan fungsi highlight baru
        hl, txt = make_text_and_highlight_frame(font, wrapped, (margin_x, y_pos), i, total_frames)
        vis = render_wipe_layer(txt, t)
        
        # Gabungkan semua layer: background, highlight, dan teks yang di-wipe
        comb = Image.alpha_composite(frame, hl)
        comb = Image.alpha_composite(comb, vis)
        
        return np.array(comb.convert("RGB"))

    return make_clip_from_generator(frame_generator, dur)

def render_penutup(dur=3.0):
# ... (Fungsi ini tetap sama) ...
    def frame_generator(i):
        return np.array(Image.new("RGB", VIDEO_SIZE, BG_COLOR))
    return make_clip_from_generator(frame_generator, dur)

# ===============================
#   OVERLAY, INPUT, OUTPUT
# ===============================

def add_overlay(base_clip):
# ... (Fungsi ini tetap sama) ...
    if not os.path.exists(OVERLAY_FILE): return base_clip
    try:
        overlay_pil = Image.open(OVERLAY_FILE).convert("RGBA")
    except Exception as e:
        print(f"❌ Error loading overlay '{OVERLAY_FILE}': {e}")
        return base_clip
    overlay_pil_resized = overlay_pil.resize(VIDEO_SIZE, Image.LANCZOS)
    overlay_clip = ImageClip(np.array(overlay_pil_resized), duration=base_clip.duration)
    return CompositeVideoClip([base_clip, overlay_clip.set_pos((0, 0))], size=VIDEO_SIZE)

def baca_semua_berita(file_path):
# ... (Fungsi ini tetap sama) ...
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ File '{file_path}' tidak ditemukan!")
        exit(1)
    except Exception as e:
        print(f"❌ Error reading file '{file_path}': {e}")
        exit(1)

    blok_berita = content.strip().split("---")
    semua_data = []
    known_keys = ["upper:", "judul:", "subjudul:"]

    for blok in blok_berita:
        lines = blok.strip().splitlines()
        data = {}
        isi_raw_start_index = -1
        i = 0
        last_processed_header_line = -1

        while i < len(lines):
            line = lines[i].strip()
            lower_line = line.lower() if line else ""
            is_potential_isi = line and last_processed_header_line != -1 and not any(lower_line.startswith(k) for k in known_keys)
            is_potential_isi_only = line and last_processed_header_line == -1 and not any(lower_line.startswith(k) for k in known_keys)
            if is_potential_isi or is_potential_isi_only:
                isi_raw_start_index = i
                break
            current_key = None
            if lower_line.startswith("upper:"):
                current_key = "Upper"
                value_part = line.split(":", 1)[1].strip()
            elif lower_line.startswith("judul:"):
                current_key = "Judul"
                value_part = line.split(":", 1)[1].strip()
            elif lower_line.startswith("subjudul:"):
                current_key = "Subjudul"
                value_part = line.split(":", 1)[1].strip()
            else:
                i += 1
                continue

            key_lines = [value_part] if value_part else []
            i += 1
            while i < len(lines):
                next_line = lines[i].strip()
                if any(next_line.lower().startswith(k) for k in known_keys): break
                if not next_line and key_lines:
                    isi_raw_start_index = i
                    break
                if next_line: key_lines.append(next_line)
                i += 1

            data[current_key] = "\n".join(key_lines)
            last_processed_header_line = i - 1

        if isi_raw_start_index != -1:
            isi_raw = lines[isi_raw_start_index:]
            isi_text = "\n".join(isi_raw).strip()
            paragraf_list = [p.strip() for p in isi_text.split("\n\n") if p.strip()]
            for idx, p in enumerate(paragraf_list, start=1):
                data[f"Isi_{idx}"] = p
        if data:
            semua_data.append(data)
    return semua_data

def buat_video(data, index=None):
# ... (Fungsi ini tetap sama) ...
    judul = data.get("Judul", "")
    print(f"▶ Membuat video: {judul}")
    try:
        opening = render_opening(
            judul, data.get("Subjudul", None), FONTS,
            upper_txt=data.get("Upper", None)
        )
        isi_clips = []
        isi_data = [f"Isi_{i}" for i in range(1, 30) if f"Isi_{i}" in data and data[f"Isi_{i}"].strip()]
        jeda = render_penutup(0.7)
        for idx, key in enumerate(isi_data):
            teks = data[key]
            dur = durasi_otomatis(teks)
            clip = render_text_block(teks, FONTS["isi"], 34, dur)
            isi_clips.append(clip)
            if idx < len(isi_data) - 1:
                isi_clips.append(jeda)
        penutup = render_penutup(4.0)
        final = concatenate_videoclips([opening] + isi_clips + [penutup], method="compose")
        result = add_overlay(final)
        filename = f"output_video_{index+1 if index is not None else '1'}.mp4"
        result.write_videofile(filename, fps=FPS, codec="libx264", audio=False, logger=None, threads=4)
        print(f"✅ Video selesai: {filename}\n")
    except Exception as e:
        print(f"❌ Gagal membuat video untuk '{judul}': {e}")

# ===============================
#   MAIN PROGRAM
# ===============================

if __name__ == "__main__":
# ... (Fungsi ini tetap sama) ...
    FILE_INPUT = "data_berita.txt"
    font_files_ok = True
    for key, font_file in FONTS.items():
        if not os.path.exists(font_file):
            print(f"❌ File Font '{font_file}' untuk '{key}' tidak ditemukan!")
            font_files_ok = False
    if not font_files_ok:
        exit(1)

    semua = baca_semua_berita(FILE_INPUT)
    if not semua:
        print(f"❌ Tidak ada data berita yang valid di '{FILE_INPUT}'.")
        exit(1)

    print(f"Total {len(semua)} video akan dibuat...")
    for i, data in enumerate(semua):
        buat_video(data, i)
    print("🎬 Semua video selesai dibuat (atau dilewati jika gagal).")
