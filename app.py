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
# VOICE CATALOGUE & MOTIVATIONAL PRESETS
# ─────────────────────────────────────────────
VOICE_OPTIONS = {
    "🇵🇰 Asad – Motivational (UR Male)": "ur-PK-AsadNeural::motivational",
    "🇵🇰 Uzma – Inspiring (UR Female)": "ur-PK-UzmaNeural::inspiring",
    "🇺🇸 Andrew – Power (EN Male)": "en-US-AndrewNeural::motivational",
    "🇺🇸 Ava – Emotional (EN Female)": "en-US-AvaNeural::inspiring",
    "🇺🇸 Guy – Deep Narrator (EN Male)": "en-US-GuyNeural::deep",
    "🇬🇧 Ryan – Professional (EN Male)": "en-GB-RyanNeural",
}

TONE_PRESETS = {
    "motivational": {"rate": "+12%", "pitch": "+2Hz"}, 
    "inspiring":    {"rate": "-5%",  "pitch": "+3Hz"}, 
    "deep":         {"rate": "-10%", "pitch": "-5Hz"}, 
    "dramatic":     {"rate": "-8%",  "pitch": "-4Hz"},
}

def resolve_voice(voice_str: str):
    """Splits voice_id and preset, returning the ID and the tone dict."""
    if "::" in voice_str:
        vid, preset = voice_str.split("::", 1)
        tone = TONE_PRESETS.get(preset, {"rate": "+0%", "pitch": "+0Hz"})
        return vid, tone
    return voice_str, {"rate": "+0%", "pitch": "+0Hz"}

# ─────────────────────────────────────────────
# AI MOTIVATIONAL DIRECTOR
# ─────────────────────────────────────────────
def get_ai_production_plan(api_key, language, story, instructions, chosen_voice_id):
    """Consults Groq Llama to write a high-impact motivational script."""
    client = Groq(api_key=api_key)

    system_prompt = (
        "You are a world-class motivational scriptwriter and director. "
        "Transform the user's story into a POWERFUL, INSPIRING narration. "
        "Use short, punchy sentences. Use rhetorical questions. "
        "Return ONLY a JSON object with EXACTLY these four keys:\n"
        "{\n"
        '  "refined_script": "The high-impact narration text",\n'
        f'  "voice": "{chosen_voice_id}",\n'
        '  "tone_settings": {{"rate": "+5%", "pitch": "+2Hz"}},\n'
        '  "bg_volume": 0.12\n'
        "}\n\n"
        f"Language: {language}. Focus on poetic and formal energy."
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
            temperature=0.7,
        )
        
        raw_content = completion.choices[0].message.content
        plan = json.loads(raw_content)
        
        # Self-healing logic to prevent TypeErrors
        if not isinstance(plan, dict): plan = {}
        plan.setdefault("refined_script", story)
        plan.setdefault("voice", chosen_voice_id)
        plan.setdefault("tone_settings", {"rate": "+0%", "pitch": "+0Hz"})
        plan.setdefault("bg_volume", 0.12)
        
        return plan
    except Exception as e:
        st.error(f"AI Director Error: {e}")
        return {
            "refined_script": story,
            "voice": chosen_voice_id,
            "tone_settings": {"rate": "+0%", "pitch": "+0Hz"},
            "bg_volume": 0.15
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
    # Merge AI settings with presets
    merged = {**preset_tone, **settings}
    try:
        asyncio.run(_generate_voice_async(text, resolved_id, merged, path))
    except Exception as e:
        st.error(f"TTS Error: {e}")

def produce_final_video(video_paths, script, config, output_path):
    """Assembles clips, generates narration, and mixes audio."""
    words = script.split()
    num_clips = len(video_paths)
    if not words: return False

    size = math.ceil(len(words) / num_clips)
    script_parts = [" ".join(words[i:i+size]) for i in range(0, len(words), size)]
    while len(script_parts) < num_clips: script_parts.append("")

    voice_str = config.get("voice", "en-US-AndrewNeural")
    tone = config.get("tone_settings", {})
    bg_vol = float(config.get("bg_volume", 0.12))

    final_segments = []
    
    try:
        for i in range(num_clips):
            st.write(f"🎙️ Narrating Segment {i+1}...")
            audio_p = os.path.join(TEMP_DIR, f"v_{i}.mp3")
            generate_voice_sync(script_parts[i], voice_str, tone, audio_p)

            voice_audio = AudioFileClip(audio_p).volumex(1.8) # Loud and clear voice
            clip = VideoFileClip(video_paths[i])
            
            # Sync video speed to voice duration
            v_duration = voice_audio.duration
            synced_v = clip.fx(vfx.speedx, clip.duration / v_duration).set_duration(v_duration)
            
            # Add cinematic fades
            synced_v = synced_v.fadein(0.4).fadeout(0.4)

            # Mix voice with lowered original clip audio (music)
            if clip.audio:
                background = clip.audio.volumex(bg_vol)
                synced_v = synced_v.set_audio(CompositeAudioClip([background, voice_audio]))
            else:
                synced_v = synced_v.set_audio(voice_audio)
            
            final_segments.append(synced_v)

        st.write("🚀 Rendering Final Motivational Masterpiece...")
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
st.set_page_config(page_title="AI Motivational Forge", page_icon="🔥", layout="wide")
st.title("🔥 AI Motivational Video Forge")

with st.sidebar:
    st.header("🔑 API Setup")
    api_key = st.text_input("Groq API Key", type="password")
    st.markdown("---")
    st.header("🎙️ Voice Settings")
    voice_label = st.selectbox("Narrator Voice", list(VOICE_OPTIONS.keys()))
    voice_id = VOICE_OPTIONS[voice_label]
    
    if st.button("🧹 Clear Temporary Files"):
        for f in os.listdir(TEMP_DIR):
            try: os.remove(os.path.join(TEMP_DIR, f))
            except: pass
        st.success("Cache Cleared")

col1, col2 = st.columns(2)
with col1:
    lang = st.selectbox("🌍 Language", ["English", "Urdu"])
    files = st.file_uploader("📹 Upload Clips (Order matters)", type=["mp4", "mov"], accept_multiple_files=True)
with col2:
    story = st.text_area("📖 Story / Concept", placeholder="Describe the struggle and the victory...", height=150)
    instr = st.text_area("🎤 Director Style", value="Dramatic, inspiring, deep cinematic pauses.", height=68)

if st.button("🔥 GENERATE CINEMATIC VIDEO", use_container_width=True, type="primary"):
    if not api_key or not files or not story:
        st.error("Missing Input: Please provide API Key, Video Files, and a Story.")
    else:
        with st.status("🛠️ AI Agent at Work...", expanded=True) as status:
            # 1. AI Scripting
            st.write("🧠 Writing Motivational Script...")
            plan = get_ai_production_plan(api_key, lang, story, instr, voice_id)
            
            if plan:
                with st.expander("📝 View AI Script"):
                    st.write(plan.get("refined_script", ""))

                # 2. Save Uploaded Files
                st.write("💾 Saving Video Data...")
                paths = []
                for i, f in enumerate(files):
                    p = os.path.join(TEMP_DIR, f"raw_{i}.mp4")
                    with open(p, "wb") as out: out.write(f.getbuffer())
                    paths.append(p)

                # 3. Produce
                out_v = os.path.join(TEMP_DIR, "final_video.mp4")
                if produce_final_video(paths, plan["refined_script"], plan, out_v):
                    status.update(label="✅ Video Forge Complete!", state="complete")
                    st.video(out_v)
                    with open(out_v, "rb") as vid:
                        st.download_button("📥 Download Final Video", vid, "motivation.mp4", "video/mp4")
                else:
                    status.update(label="❌ Video Assembly Failed", state="error")
