import streamlit as st
import os
import asyncio
import edge_tts
import json
import math
from groq import Groq

# --- MoviePy Core Imports ---
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips
import moviepy.video.fx.all as vfx

# --- Setup ---
TEMP_DIR = "temp_output"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# ─────────────────────────────────────────────
# VOICE CATALOGUE  (shown in the UI dropdown)
# ─────────────────────────────────────────────
VOICE_OPTIONS = {

    # ── Urdu – Pakistan ───────────────────────────────────────────────────
    # Microsoft edge-tts ships exactly two ur-PK voices; tone variants are
    # created via pitch/rate tweaks applied at render time (see TONE_PRESETS).
    "🇵🇰 Asad – Natural (UR Male)"          : "ur-PK-AsadNeural",
    "🇵🇰 Asad – Deep & Slow (UR Male)"      : "ur-PK-AsadNeural::deep",
    "🇵🇰 Asad – Energetic (UR Male)"        : "ur-PK-AsadNeural::energetic",
    "🇵🇰 Asad – Dramatic (UR Male)"         : "ur-PK-AsadNeural::dramatic",
    "🇵🇰 Asad – Calm Documentary (UR Male)" : "ur-PK-AsadNeural::documentary",
    "🇵🇰 Uzma – Natural (UR Female)"        : "ur-PK-UzmaNeural",
    "🇵🇰 Uzma – Warm & Slow (UR Female)"    : "ur-PK-UzmaNeural::warm",
    "🇵🇰 Uzma – Energetic (UR Female)"      : "ur-PK-UzmaNeural::energetic",
    "🇵🇰 Uzma – Dramatic (UR Female)"       : "ur-PK-UzmaNeural::dramatic",
    "🇵🇰 Uzma – Calm Documentary (UR Female)": "ur-PK-UzmaNeural::documentary",

    # ── English – United States ───────────────────────────────────────────
    "🇺🇸 Andrew – Natural (EN Male)"        : "en-US-AndrewNeural",
    "🇺🇸 Andrew – Deep & Slow (EN Male)"    : "en-US-AndrewNeural::deep",
    "🇺🇸 Ava – Natural (EN Female)"         : "en-US-AvaNeural",
    "🇺🇸 Ava – Warm (EN Female)"            : "en-US-AvaNeural::warm",
    "🇺🇸 Eric – Natural (EN Male)"          : "en-US-EricNeural",
    "🇺🇸 Guy – Natural (EN Male)"           : "en-US-GuyNeural",
    "🇺🇸 Jenny – Natural (EN Female)"       : "en-US-JennyNeural",
    "🇺🇸 Aria – Natural (EN Female)"        : "en-US-AriaNeural",
    "🇺🇸 Davis – Natural (EN Male)"         : "en-US-DavisNeural",
    "🇺🇸 Tony – Natural (EN Male)"          : "en-US-TonyNeural",
    "🇺🇸 Sara – Natural (EN Female)"        : "en-US-SaraNeural",
    "🇺🇸 Jason – Natural (EN Male)"         : "en-US-JasonNeural",
    "🇺🇸 Nancy – Natural (EN Female)"       : "en-US-NancyNeural",

    # ── English – United Kingdom ──────────────────────────────────────────
    "🇬🇧 Sonia – Natural (EN Female)"       : "en-GB-SoniaNeural",
    "🇬🇧 Ryan – Natural (EN Male)"          : "en-GB-RyanNeural",
    "🇬🇧 Libby – Natural (EN Female)"       : "en-GB-LibbyNeural",
    "🇬🇧 Thomas – Natural (EN Male)"        : "en-GB-ThomasNeural",
}

# ─────────────────────────────────────────────────────────────────────────────
# TONE PRESETS  –  applied when a voice label ends with "::<preset>"
# These shift pitch / rate to simulate different "people" with the same voice.
# ─────────────────────────────────────────────────────────────────────────────
TONE_PRESETS = {
    "deep"        : {"rate": "-12%", "pitch": "-8Hz"},
    "energetic"   : {"rate": "+18%", "pitch": "+4Hz"},
    "dramatic"    : {"rate": "-8%",  "pitch": "-4Hz"},
    "documentary" : {"rate": "-5%",  "pitch": "-2Hz"},
    "warm"        : {"rate": "-6%",  "pitch": "+2Hz"},
}

def resolve_voice(voice_str: str):
    """Split 'voice_id::preset' → (voice_id, tone_dict)."""
    if "::" in voice_str:
        vid, preset = voice_str.split("::", 1)
        tone = TONE_PRESETS.get(preset, {"rate": "+0%", "pitch": "+0Hz"})
        return vid, tone
    return voice_str, {"rate": "+0%", "pitch": "+0Hz"}

# ─────────────────────────────────────────────
# AI DIRECTOR  –  Strict prompt → no more 400s
# ─────────────────────────────────────────────
def get_ai_production_plan(api_key, language, story, instructions, chosen_voice_id):
    """
    Ask Llama to return ONLY the four keys we need.
    The system prompt is intentionally short and ultra-specific to prevent
    the model from inventing extra keys (films, storyboard, etc.) that break
    JSON validation on Groq's side.
    """
    client = Groq(api_key=api_key)

    system_prompt = (
        "You are an AI video scriptwriter. "
        "Return ONLY a JSON object with EXACTLY these four keys and no others:\n"
        "{\n"
        '  "refined_script": "<full narration as a single plain string>",\n'
        f'  "voice": "{chosen_voice_id}",\n'
        '  "tone_settings": {"rate": "+0%", "pitch": "+0Hz"},\n'
        '  "bg_volume": 0.15\n'
        "}\n\n"
        f"Language: {language}. "
        "Adjust rate/pitch subtly based on the director's mood instructions. "
        "bg_volume must be between 0.05 and 0.30. "
        "Do NOT add any extra keys, arrays, or nested objects beyond the structure above."
    )

    user_msg = (
        f"Story / Description:\n{story}\n\n"
        f"Director Instructions:\n{instructions}"
    )

    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,   # lower temp → more deterministic / schema-safe
        )
        raw = completion.choices[0].message.content
        plan = json.loads(raw)

        # ── Self-healing ──────────────────────────────────────────────────
        # voice ended up as a dict?
        if isinstance(plan.get("voice"), dict):
            plan["voice"] = plan["voice"].get("id", chosen_voice_id)

        # refined_script ended up as a dict?
        if isinstance(plan.get("refined_script"), dict):
            plan["refined_script"] = plan["refined_script"].get(
                "text", str(plan["refined_script"])
            )

        # model ignored us and nested everything under a key like "film"?
        for unwanted in ("films", "film", "storyboard", "segments"):
            if unwanted in plan and "refined_script" not in plan:
                st.warning(
                    f"AI returned unexpected key '{unwanted}'. Extracting script…"
                )
                inner = plan[unwanted]
                if isinstance(inner, list) and inner:
                    inner = inner[0]
                if isinstance(inner, dict):
                    plan["refined_script"] = inner.get("refined_script", story)
                    plan.setdefault("voice", chosen_voice_id)
                    plan.setdefault("tone_settings", {"rate": "+0%", "pitch": "+0Hz"})
                    plan.setdefault("bg_volume", 0.15)
                break

        # Final fallback – ensure all required keys exist
        plan.setdefault("refined_script", story)
        plan.setdefault("voice", chosen_voice_id)
        plan.setdefault("tone_settings", {"rate": "+0%", "pitch": "+0Hz"})
        plan.setdefault("bg_volume", 0.15)

        return plan

    except json.JSONDecodeError as e:
        st.error(f"JSON parse error (AI returned invalid JSON): {e}")
        return None
    except Exception as e:
        st.error(f"AI Director Error: {e}")
        return None


# ─────────────────────────────────────────────
# AUDIO ENGINE
# ─────────────────────────────────────────────
async def _generate_voice_async(text, voice, settings, path):
    if not isinstance(settings, dict):
        settings = {}
    rate  = settings.get("rate",  "+0%")
    pitch = settings.get("pitch", "+0Hz")
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(path)


def generate_voice_sync(text, voice_str, settings, path):
    """
    Resolve any '::preset' suffix, merge tone overrides, then run TTS.
    'settings' from the AI plan can still override the preset values.
    """
    resolved_id, preset_tone = resolve_voice(voice_str)

    # AI plan tone takes precedence only if it's non-default
    merged = dict(preset_tone)
    if isinstance(settings, dict):
        for k in ("rate", "pitch"):
            ai_val = settings.get(k)
            if ai_val and ai_val not in ("+0%", "+0Hz"):
                merged[k] = ai_val

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _generate_voice_async(text, resolved_id, merged, path))
                future.result()
        else:
            loop.run_until_complete(_generate_voice_async(text, resolved_id, merged, path))
    except RuntimeError:
        asyncio.run(_generate_voice_async(text, resolved_id, merged, path))


# ─────────────────────────────────────────────
# VIDEO ENGINE
# ─────────────────────────────────────────────
def produce_final_video(video_paths, script, config, output_path):
    if not isinstance(script, str):
        script = str(script)

    num_clips = len(video_paths)
    words = script.split()
    if not words:
        st.error("Script is empty – cannot produce video.")
        return False

    # Split script evenly across clips
    size = math.ceil(len(words) / num_clips)
    script_parts = [
        " ".join(words[i : i + size]) for i in range(0, len(words), size)
    ]
    while len(script_parts) < num_clips:
        script_parts.append(script_parts[-1] if script_parts else "")

    voice_str  = config.get("voice", "en-US-AvaNeural")
    tone       = config.get("tone_settings", {})
    bg_vol     = float(config.get("bg_volume", 0.15))

    final_segments = []

    try:
        for i in range(num_clips):
            st.write(f"🎞️ Syncing segment {i + 1} / {num_clips}…")
            audio_path = os.path.join(TEMP_DIR, f"voice_{i}.mp3")

            generate_voice_sync(script_parts[i], voice_str, tone, audio_path)

            voice_audio = AudioFileClip(audio_path).volumex(1.6)
            clip        = VideoFileClip(video_paths[i])

            # Speed-match video to narration length
            speed_factor = clip.duration / voice_audio.duration
            synced_v     = clip.fx(vfx.speedx, speed_factor).set_duration(voice_audio.duration)

            if clip.audio is not None:
                bg_audio = clip.audio.volumex(bg_vol)
                synced_v = synced_v.set_audio(CompositeAudioClip([bg_audio, voice_audio]))
            else:
                synced_v = synced_v.set_audio(voice_audio)

            final_segments.append(synced_v)

        st.write("🚀 Rendering final MP4…")
        final_video = concatenate_videoclips(final_segments, method="compose")
        final_video.write_videofile(
            output_path, fps=24, codec="libx264", audio_codec="aac"
        )
        return True

    except Exception as e:
        st.error(f"Production Error: {e}")
        import traceback
        st.code(traceback.format_exc())
        return False

    finally:
        for seg in final_segments:
            try:
                seg.close()
            except Exception:
                pass


# ─────────────────────────────────────────────
# STREAMLIT UI
# ─────────────────────────────────────────────
st.set_page_config(page_title="AI Video Forge", page_icon="🎬", layout="wide")

# ── Sidebar ───────────────────────────────────
with st.sidebar:
    st.title("🔑 Setup")
    api_key = st.text_input("Groq API Key", type="password")

    st.markdown("---")
    st.subheader("🎙️ Voice Selection")

    # Group filter
    lang_filter = st.radio("Filter by language", ["All", "🇵🇰 Urdu", "🇺🇸🇬🇧 English"], horizontal=True)

    def _filter(label):
        if lang_filter == "All":
            return True
        if lang_filter == "🇵🇰 Urdu":
            return "🇵🇰" in label
        return "🇺🇸" in label or "🇬🇧" in label

    filtered_voices = {k: v for k, v in VOICE_OPTIONS.items() if _filter(k)}
    chosen_voice_label = st.selectbox("Choose a narrator voice", list(filtered_voices.keys()))
    chosen_voice_id    = filtered_voices[chosen_voice_label]

    # Show resolved ID and preset
    base_id, preset_tone = resolve_voice(chosen_voice_id)
    st.caption(f"Voice ID: `{base_id}`")
    if "::" in chosen_voice_id:
        preset_name = chosen_voice_id.split("::")[1]
        st.info(f"🎚️ Tone preset: **{preset_name}** → rate `{preset_tone['rate']}`, pitch `{preset_tone['pitch']}`")

    st.markdown("---")
    if st.button("🧹 Clear Temp Cache"):
        for f in os.listdir(TEMP_DIR):
            try:
                os.remove(os.path.join(TEMP_DIR, f))
            except Exception:
                pass
        st.success("Cache cleared!")

# ── Main ──────────────────────────────────────
st.title("🤖 AI Agent Video Forge")
st.caption("Upload clips + description → AI writes script → synced narrated video")

col_a, col_b = st.columns([1, 1])
with col_a:
    language = st.selectbox("🌍 Narration Language", ["English", "Urdu"])
with col_b:
    uploaded_files = st.file_uploader(
        "📹 Upload Video Clips (order matters)",
        type=["mp4", "mov"],
        accept_multiple_files=True,
    )

col_c, col_d = st.columns([1, 1])
with col_c:
    user_story = st.text_area(
        "📖 Description / Story",
        placeholder="Describe what each clip is about, or paste your full story…",
        height=200,
    )
with col_d:
    user_instructions = st.text_area(
        "🎤 Director's Instructions",
        placeholder="e.g. 'Dramatic tone, slow pace', 'Upbeat and energetic', 'Emotional and cinematic'…",
        height=200,
    )

# ── Preview chosen voice ──────────────────────
with st.expander("🔊 Preview Selected Voice"):
    _default_test = (
        "خوش آمدید! یہ آواز کا نمونہ ہے۔"
        if "🇵🇰" in chosen_voice_label
        else "Welcome to the AI Video Forge. This is a voice preview."
    )
    test_text = st.text_input("Test sentence", value=_default_test)
    if st.button("▶ Preview Voice"):
        prev_path = os.path.join(TEMP_DIR, "preview.mp3")
        with st.spinner("Generating preview…"):
            generate_voice_sync(test_text, chosen_voice_id, {}, prev_path)
        st.audio(prev_path)

# ── Generate ──────────────────────────────────
if st.button("🔥 Generate AI Video", use_container_width=True, type="primary"):
    if not api_key:
        st.error("⛔ Please enter your Groq API Key in the sidebar.")
    elif not user_story.strip():
        st.warning("⚠️ Please enter a story / description.")
    elif not uploaded_files:
        st.warning("⚠️ Please upload at least one video clip.")
    else:
        with st.status("🛠️ AI Agent working…", expanded=True) as status:

            # 1. Get AI production plan
            st.write("🧠 Consulting AI Director…")
            plan = get_ai_production_plan(
                api_key, language, user_story, user_instructions, chosen_voice_id
            )

            if not plan or not isinstance(plan, dict):
                status.update(label="❌ AI Director failed.", state="error")
                st.stop()

            # Show the plan
            with st.expander("📋 AI Production Plan"):
                st.json(plan)

            # 2. Save uploaded clips to disk
            st.write("💾 Saving uploaded clips…")
            video_paths = []
            for i, f in enumerate(uploaded_files):
                p = os.path.join(TEMP_DIR, f"raw_{i}.mp4")
                with open(p, "wb") as out:
                    out.write(f.getbuffer())
                video_paths.append(p)

            # 3. Produce video
            out_path = os.path.join(TEMP_DIR, "final_video.mp4")
            success  = produce_final_video(video_paths, plan.get("refined_script", user_story), plan, out_path)

            if success:
                status.update(label="✅ Video ready!", state="complete")
                st.video(out_path)
                with open(out_path, "rb") as vid:
                    st.download_button(
                        "📥 Download Video",
                        vid,
                        file_name="AI_Video.mp4",
                        mime="video/mp4",
                        use_container_width=True,
                    )
            else:
                status.update(label="❌ Production failed. See errors above.", state="error")
