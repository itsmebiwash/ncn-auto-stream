import os
import numpy as np
from PIL import Image
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, ColorClip


def _pil_resize(img_array, target_w, target_h):
    """Resize a numpy array image using PIL (avoids moviepy's ANTIALIAS bug)."""
    pil_img = Image.fromarray(img_array.astype("uint8"))
    pil_img = pil_img.resize((target_w, target_h), Image.LANCZOS)
    return np.array(pil_img)


def generate_news_reel(image_card_path, headline, output_path, duration=10):
    """
    Generates a 9:16 vertical video reel (1080x1920) with Ken Burns zoom.
    Uses PIL for resizing to avoid moviepy/Pillow 10+ ANTIALIAS compatibility bug.
    """
    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        W, H = 1080, 1920

        # --- Load and resize news card using PIL (avoids PIL.ANTIALIAS bug) ---
        pil_card = Image.open(image_card_path).convert("RGB")
        card_orig_w, card_orig_h = pil_card.size
        scale = W / card_orig_w
        new_h = int(card_orig_h * scale)
        pil_card = pil_card.resize((W, new_h), Image.LANCZOS)
        card_array = np.array(pil_card)

        # --- Ken Burns zoom effect ---
        y_offset = max(0, (H - new_h) // 2)

        def make_card_frame(t):
            """Apply subtle Ken Burns zoom to the card."""
            zoom = 1.0 + 0.06 * (t / duration)  # 1.0 → 1.06
            zoomed_w = int(W / zoom)
            zoomed_h = int(new_h / zoom)
            left = (W - zoomed_w) // 2
            top = (new_h - zoomed_h) // 2
            cropped = Image.fromarray(card_array).crop(
                (left, top, left + zoomed_w, top + zoomed_h)
            )
            cropped = cropped.resize((W, new_h), Image.LANCZOS)
            # Place on black canvas
            canvas = np.zeros((H, W, 3), dtype=np.uint8)
            canvas[y_offset: y_offset + new_h, :, :] = np.array(cropped)
            return canvas

        # Create card clip using make_frame (avoids moviepy resize entirely)
        card_clip = ImageClip(make_card_frame(0)).set_duration(duration)
        # Use fl (not fl_image) with t parameter for animation
        from moviepy.video.VideoClip import VideoClip
        animated_clip = VideoClip(make_card_frame, duration=duration)

        # --- Background: black ---
        bg_color = ColorClip(size=(W, H), color=(10, 10, 15)).set_duration(duration)

        # --- Composite ---
        video = CompositeVideoClip([bg_color, animated_clip], size=(W, H))

        # --- Audio (optional) ---
        audio_path = os.path.join(os.path.dirname(__file__), "..", "assets", "news_beat.mp3")
        if os.path.exists(audio_path):
            try:
                from moviepy.audio.fx.all import audio_loop, audio_fadeout
                audio = AudioFileClip(audio_path)
                if audio.duration < duration:
                    audio = audio_loop(audio, duration=duration)
                else:
                    audio = audio.subclip(0, duration)
                audio = audio_fadeout(audio, 1.5)
                video = video.set_audio(audio)
            except Exception as ae:
                print(f"[Reel Audio Warning] {ae} — Skipping audio.")

        video.write_videofile(
            output_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            logger=None,
            threads=2
        )
        print(f"[Reel Generator] Saved: {output_path}")
        return output_path

    except Exception as e:
        print(f"[Reel Generator Error] {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    generate_news_reel("test_card.jpg", "Test Headline", "test_reel.mp4")
