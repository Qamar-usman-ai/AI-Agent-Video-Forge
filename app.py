import streamlit as st
import os
import asyncio
import edge_tts
import json
import math
import re
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
    "🇺🇸 Guy – Movie Trailer (EN Male)": "en-US-GuyNeural::dramatic",
    "🇺🇸 Andrew – Power (EN Male)": "en-US-AndrewNeural::motivational",
    "🇺🇸 Ava – Emotional (EN Female)": "en-US-AvaNeural::inspiring",
    "🇬🇧 Thomas – Stoic (EN Male)": "en-GB-ThomasNeural::deep",
    "🇵🇰 Asad – Motivational (UR Male)": "ur-PK-AsadNeural::motivational",
}

TONE_PRESETS = {
    "motivational": {"rate": "-5%", "pitch": "+0Hz"}, 
    "inspiring":    {"rate": "-10%", "pitch": "+2Hz"},
    "deep":         {"rate": "-15%", "pitch": "-5Hz"}, 
    "dramatic":     {"rate": "-12%", "pitch": "-3Hz"},
}

def resolve_voice(voice_str: str):
    if "::" in voice_str:
        vid, preset = voice_str.split("::", 1)
        tone = TONE_PRESETS.get(preset, {"rate": "-10%", "pitch": "+0Hz"})
        return vid, tone
    return voice_str, {"rate": "-10%", "pitch": "+0Hz"}

# ─────────────────────────────────────────────
# AI EMOTIONAL DIRECTOR (GROQ)
# ─────────────────────────────────────────────
def get_ai_production_plan(api_key, language, story, instructions, chosen_voice_id):
    client = Groq(api_key=api_key)
    system_prompt = (
        "You are a cinematic scriptwriter. Transform the story into a DEEP, EMOTIONAL narration. "
        "Use short sentences. Use '...' for dramatic pauses. "
        "Focus on the struggle and the ultimate victory. "
        "Return ONLY a JSON object with these keys: "
        '{"refined_script": "...", "voice": "...", "tone_settings": {"rate": "-15%", "pitch": "-2Hz"}, "bg_volume": 0.15}'
    )
    user_msg = f"Language: {language}\nStory: {story}\nStyle: {instructions}"

    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}],
            response_format={"type": "json_object"},
        )
        plan = json.loads(completion.choices[0].message.content)
        return plan
    except Exception as e:
        st.error(f"AI Director Error: {e}")
        return {"refined_script": story, "voice": chosen_voice_id, "tone_settings": {"rate": "-10%"}, "bg_volume": 0.20}

# ─────────────────────────────────────────────
# AUDIO ENGINE (SSML FOR PAUSES)
# ─────────────────────────────────────────────
async def _generate_voice_async(text, voice, settings, path):
    rate = settings.get("rate", "-10%")
    pitch = settings.get("pitch", "+0Hz")
    
    # Convert '...' into 1.5 second breaks for emotional impact
    clean_text = text.replace("...", '<break time="1500ms"/>')
    ssml = f"""
    <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
        <voice name="{voice}">
            <prosody rate="{rate}" pitch="{pitch}">
                {clean_text}
            </prosody>
        </voice>
    </speak>
    """
    communicate = edge_tts.Communicate(ssml, voice)
    await communicate.save(path)

def generate_voice_sync(text, voice_str, settings, path):
    vid, preset_tone = resolve_voice(voice_str)
    merged = {**preset_tone, **settings}
    try:
        asyncio.run(_generate_voice_async(text, vid, merged, path))
    except Exception as e:
        st.error(f"TTS Error: {e}")

# ─────────────────────────────────────────────
# VIDEO PRODUCTION ENGINE
# ─────────────────────────────────────────────
def produce_final_video(video_paths, script, config, output_path, master_bg_path=None):
    words = script.split()
    num_clips = len(video_paths)
    size = math.ceil(len(words) / num_clips)
    script_parts = [" ".join(words[i:i+size]) for i in range(0, len(words), size)]
    
    voice_str = config.get("voice", "en-US-GuyNeural")
    tone = config.get("tone_settings", {"rate": "-12%"})
    
    final_segments = []
    
    try:
        for i in range(num_clips):
            st.write(f"🎭 Creating Scene {i+1}...")
            audio_p = os.path.join(TEMP_DIR, f"v_{i}.mp3")
            generate_voice_sync(script_parts[i], voice_str, tone, audio_p)

            voice_audio = AudioFileClip(audio_p).volumex(2.8) # Strong Voice
            clip = VideoFileClip(video_paths[i])
            
            # Match clip length to voice duration
            synced_v = clip.fx(vfx.speedx, clip.duration / voice_audio.duration).set_duration(voice_audio.duration)
            
            # Combine clip audio (if exists) with voice
            if clip.audio:
                clip_audio = clip.audio.volumex(0.15) # Duck original clip sound
                synced_v = synced_v.set_audio(CompositeAudioClip([clip_audio, voice_audio]))
            else:
                synced_v = synced_v.set_audio(voice_audio)
            
            final_segments.append(synced_v.fadein(0.5).fadeout(0.5))

        # Merge all clips
        final_video = concatenate_videoclips(final_segments, method="compose")

        # Layer 3: Master Background Music (Epic Sound)
        if master_bg_path:
            st.write("🎵 Layering Master Motivational Score...")
            master_bg = AudioFileClip(master_bg_path).volumex(0.20)
            if master_bg.duration < final_video.duration:
                master_bg = master_bg.fx(vfx.loop, duration=final_video.duration)
            else:
                master_bg = master_bg.set_duration(final_video.duration)
            
            final_audio = CompositeAudioClip([master_bg, final_video.audio])
            final_video = final_video.set_audio(final_audio)

        final_video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")
        return True
    except Exception as e:
        st.error(f"Production Failed: {e}")
        return False

# ─────────────────────────────────────────────
# STREAMLIT INTERFACE
# ─────────────────────────────────────────────
st.set_page_config(page_title="AI Epic Forge", layout="wide")
st.title("🔥 AI Cinematic Motivational Forge")

with st.sidebar:
    api_key = st.text_input("Groq API Key", type="password")
    voice_label = st.selectbox("Narrator Voice", list(VOICE_OPTIONS.keys()))
    epic_bg = st.file_uploader("🎵 Master Motivational Music (Optional)", type=["mp3", "wav"])
    if st.button("🧹 Reset Cache"):
        for f in os.listdir(TEMP_DIR): os.remove(os.path.join(TEMP_DIR, f))

col1, col2 = st.columns(2)
with col1:
    lang = st.selectbox("Language", ["English", "Urdu"])
    files = st.file_uploader("📹 Upload Video Clips", type=["mp4", "mov"], accept_multiple_files=True)
with col2:
    story = st.text_area("📖 The Story (Emotional Context)", height=150)
    instr = st.text_area("🎤 Narrator Style", value="Deep, raspy, slow, cinematic pauses.")

if st.button("🚀 GENERATE CINEMATIC MASTERPIECE", use_container_width=True, type="primary"):
    if not api_key or not files or not story:
        st.error("Fill in all fields!")
    else:
        with st.status("🎬 Processing...") as status:
            plan = get_ai_production_plan(api_key, lang, story, instr, VOICE_OPTIONS[voice_label])
            
            # Save inputs
            video_paths = []
            for i, f in enumerate(files):
                p = os.path.join(TEMP_DIR, f"input_{i}.mp4")
                with open(p, "wb") as out: out.write(f.getbuffer())
                video_paths.append(p)
            
            bg_p = None
            if epic_bg:
                bg_p = os.path.join(TEMP_DIR, "master_bg.mp3")
                with open(bg_p, "wb") as out: out.write(epic_bg.getbuffer())

            out_v = os.path.join(TEMP_DIR, "final.mp4")
            if produce_final_video(video_paths, plan["refined_script"], plan, out_v, bg_p):
                st.video(out_v)
                with open(out_v, "rb") as vid:
                    st.download_button("📥 Download Masterpiece", vid, "motivation.mp4")
                status.update(label="✅ Success!", state="complete")
