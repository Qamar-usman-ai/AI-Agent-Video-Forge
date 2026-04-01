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
# VOICE CATALOGUE & EMOTIONAL PRESETS
# ─────────────────────────────────────────────
VOICE_OPTIONS = {
    "🇺🇸 Andrew – Power (EN Male)": "en-US-AndrewNeural::motivational",
    "🇺🇸 Ava – Emotional (EN Female)": "en-US-AvaNeural::inspiring",
    "🇵🇰 Asad – Motivational (UR Male)": "ur-PK-AsadNeural::motivational",
    "🇵🇰 Uzma – Inspiring (UR Female)": "ur-PK-UzmaNeural::inspiring",
    "🇺🇸 Guy – Deep Narrator (EN Male)": "en-US-GuyNeural::deep",
    "🇬🇧 Ryan – Professional (EN Male)": "en-GB-RyanNeural",
}

TONE_PRESETS = {
    "motivational": {"rate": "+5%", "pitch": "+0Hz"}, 
    "inspiring":    {"rate": "-10%", "pitch": "+2Hz"}, # Slower for emotion
    "deep":         {"rate": "-12%", "pitch": "-5Hz"}, 
    "dramatic":     {"rate": "-15%", "pitch": "-3Hz"},
}

def resolve_voice(voice_str: str):
    if "::" in voice_str:
        vid, preset = voice_str.split("::", 1)
        tone = TONE_PRESETS.get(preset, {"rate": "+0%", "pitch": "+0Hz"})
        return vid, tone
    return voice_str, {"rate": "+0%", "pitch": "+0Hz"}

# ─────────────────────────────────────────────
# AI EMOTIONAL DIRECTOR (GROQ)
# ─────────────────────────────────────────────
def get_ai_production_plan(api_key, language, story, instructions, chosen_voice_id):
    client = Groq(api_key=api_key)

    system_prompt = (
        "You are an award-winning emotional storyteller and cinematic director. "
        "Transform the user's input into a deeply moving, soul-stirring speech. "
        "Use poetic language, dramatic pauses (marked with ...), and emotional weight. "
        "Return ONLY a JSON object with EXACTLY these four keys:\n"
        "{\n"
        '  "refined_script": "The emotional narration text",\n'
        f'  "voice": "{chosen_voice_id}",\n'
        '  "tone_settings": {{"rate": "-10%", "pitch": "-2Hz"}},\n'
        '  "bg_volume": 0.20\n'
        "}\n\n"
        f"Language: {language}. Focus on heart-touching energy."
    )

    user_msg = f"Story/Context: {story}\nDirector Mood: {instructions}"

    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.75,
        )
        
        plan = json.loads(completion.choices[0].message.content)
        if not isinstance(plan, dict): plan = {}
        plan.setdefault("refined_script", story)
        plan.setdefault("voice", chosen_voice_id)
        plan.setdefault("tone_settings", {"rate": "-10%", "pitch": "+0Hz"})
        plan.setdefault("bg_volume", 0.20)
        return plan
    except Exception as e:
        st.error(f"AI Director Error: {e}")
        return {
            "refined_script": story,
            "voice": chosen_voice_id,
            "tone_settings": {"rate": "-10%", "pitch": "+0Hz"},
            "bg_volume": 0.25
        }

# ─────────────────────────────────────────────
# AUDIO & VIDEO ENGINES
# ─────────────────────────────────────────────
async def _generate_voice_async(text, voice, settings, path):
    rate = settings.get("rate", "+0%")
    pitch = settings.get("pitch", "+0Hz")
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(path)

def generate_voice_sync(text, voice_str, settings, path):
    resolved_id, preset_tone = resolve_voice(voice_str)
    merged = {**preset_tone, **settings}
    try:
        asyncio.run(_generate_voice_async(text, resolved_id, merged, path))
    except Exception as e:
        st.error(f"TTS Error: {e}")

def produce_final_video(video_paths, script, config, output_path):
    words = script.split()
    num_clips = len(video_paths)
    if not words: return False

    # Divide script among clips
    size = math.ceil(len(words) / num_clips)
    script_parts = [" ".join(words[i:i+size]) for i in range(0, len(words), size)]
    while len(script_parts) < num_clips: script_parts.append("")

    voice_str = config.get("voice", "en-US-AndrewNeural")
    tone = config.get("tone_settings", {"rate": "-10%"})
    bg_vol = float(config.get("bg_volume", 0.20)) # Volume level for original music

    final_segments = []
    
    try:
        for i in range(num_clips):
            st.write(f"🎙️ Recording Emotional Part {i+1}...")
            audio_p = os.path.join(TEMP_DIR, f"v_{i}.mp3")
            generate_voice_sync(script_parts[i], voice_str, tone, audio_p)

            voice_audio = AudioFileClip(audio_p).volumex(2.0) # High clarity for speech
            clip = VideoFileClip(video_paths[i])
            
            # Sync video duration to speech length
            v_duration = voice_audio.duration
            synced_v = clip.fx(vfx.speedx, clip.duration / v_duration).set_duration(v_duration)
            
            # CINEMATIC AUDIO MIXING: Keep original music but lower it
            if clip.audio:
                background_music = clip.audio.volumex(bg_vol)
                # Combine original music with the AI speech
                mixed_audio = CompositeAudioClip([background_music, voice_audio])
                synced_v = synced_v.set_audio(mixed_audio)
            else:
                synced_v = synced_v.set_audio(voice_audio)
            
            synced_v = synced_v.fadein(0.6).fadeout(0.6)
            final_segments.append(synced_v)

        st.write("🚀 Rendering Masterpiece...")
        final_video = concatenate_videoclips(final_segments, method="compose")
        final_video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")
        return True
    except Exception as e:
        st.error(f"Production Error: {e}")
        return False
    finally:
        for s in final_segments: s.close()

# ─────────────────────────────────────────────
# STREAMLIT UI
# ─────────────────────────────────────────────
st.set_page_config(page_title="Emotional Video Forge", page_icon="✨", layout="wide")
st.title("✨ AI Emotional & Motivational Forge")

with st.sidebar:
    st.header("🔑 Setup")
    api_key = st.text_input("Groq API Key", type="password")
    st.markdown("---")
    st.header("🎙️ Voice Selection")
    voice_label = st.selectbox("Narrator", list(VOICE_OPTIONS.keys()))
    voice_id = VOICE_OPTIONS[voice_label]
    
    if st.button("🧹 Clear Cache"):
        for f in os.listdir(TEMP_DIR):
            try: os.remove(os.path.join(TEMP_DIR, f))
            except: pass
        st.success("Cleaned!")

col1, col2 = st.columns(2)
with col1:
    lang = st.selectbox("🌍 Language", ["English", "Urdu"])
    files = st.file_uploader("📹 Upload Clips (Music from these will be kept)", type=["mp4", "mov"], accept_multiple_files=True)
with col2:
    story = st.text_area("📖 Story / Soul of the Video", placeholder="e.g., A person losing everything but finding hope in the rain...", height=150)
    instr = st.text_area("🎤 Delivery Style", value="Emotional, slow, cinematic, deep breathing pauses.", height=68)

if st.button("🔥 GENERATE EMOTIONAL VIDEO", use_container_width=True, type="primary"):
    if not api_key or not files or not story:
        st.error("Please provide API Key, Video Files, and the Story.")
    else:
        with st.status("🎬 Production in progress...", expanded=True) as status:
            # 1. AI Scripting
            st.write("🧠 Writing Emotional Narration...")
            plan = get_ai_production_plan(api_key, lang, story, instr, voice_id)
            
            if plan:
                with st.expander("📝 View Generated Script"):
                    st.write(plan.get("refined_script", ""))

                # 2. Save Uploaded Files
                st.write("💾 Processing Clips...")
                paths = []
                for i, f in enumerate(files):
                    p = os.path.join(TEMP_DIR, f"raw_{i}.mp4")
                    with open(p, "wb") as out: out.write(f.getbuffer())
                    paths.append(p)

                # 3. Produce
                out_v = os.path.join(TEMP_DIR, "final_master.mp4")
                if produce_final_video(paths, plan["refined_script"], plan, out_v):
                    status.update(label="✅ Cinematic Masterpiece Ready!", state="complete")
                    st.video(out_v)
                    with open(out_v, "rb") as vid:
                        st.download_button("📥 Download Video", vid, "emotional_story.mp4", "video/mp4")
                else:
                    status.update(label="❌ Production Failed", state="error")
