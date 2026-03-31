import streamlit as st
import os
import asyncio
import edge_tts
import json
import math
import random
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
    "motivational": {"rate": "+10%", "pitch": "+2Hz"}, # Slightly faster, energetic
    "inspiring":    {"rate": "-5%",  "pitch": "+3Hz"}, # Breathier, emotional
    "deep":         {"rate": "-10%", "pitch": "-5Hz"}, # Authority, gravity
    "dramatic":     {"rate": "-8%",  "pitch": "-4Hz"},
}

def resolve_voice(voice_str: str):
    if "::" in voice_str:
        vid, preset = voice_str.split("::", 1)
        tone = TONE_PRESETS.get(preset, {"rate": "+0%", "pitch": "+0Hz"})
        return vid, tone
    return voice_str, {"rate": "+0%", "pitch": "+0Hz"}

# ─────────────────────────────────────────────
# AI MOTIVATIONAL DIRECTOR
# ─────────────────────────────────────────────
def get_ai_production_plan(api_key, language, story, instructions, chosen_voice_id):
    client = Groq(api_key=api_key)

    system_prompt = (
        "You are a world-class motivational scriptwriter and video director. "
        "Your goal is to turn the user's story into a POWERFUL, INSPIRING, and HIGH-IMPACT script. "
        "Use short, punchy sentences. Use rhetorical questions. Create a sense of urgency and greatness. "
        "Return ONLY a JSON object with EXACTLY these four keys:\n"
        "{\n"
        '  "refined_script": "<The high-impact motivational narration>",\n'
        f'  "voice": "{chosen_voice_id}",\n'
        '  "tone_settings": {"rate": "+5%", "pitch": "+2Hz"},\n'
        '  "bg_volume": 0.12\n'
        "}\n\n"
        f"Language: {language}. If Urdu, use poetic and formal 'Muqalami' style. "
        "Do not provide any conversational text outside the JSON."
    )

    user_msg = f"Story: {story}\nDirector Mood: {instructions} (Make it deeply motivational)"

    try:
        completion = client.chat.completions.create(
            model="llama-3.1-70b-versatile", # Using 70b for better creative writing
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.7, 
        )
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        st.error(f"AI Director Error: {e}")
        return None

# ─────────────────────────────────────────────
# AUDIO & VIDEO ENGINE
# ─────────────────────────────────────────────
async def _generate_voice_async(text, voice, settings, path):
    rate = settings.get("rate", "+0%")
    pitch = settings.get("pitch", "+0Hz")
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(path)

def generate_voice_sync(text, voice_str, settings, path):
    resolved_id, preset_tone = resolve_voice(voice_str)
    merged = {**preset_tone, **settings}
    asyncio.run(_generate_voice_async(text, resolved_id, merged, path))

def produce_final_video(video_paths, script, config, output_path):
    words = script.split()
    num_clips = len(video_paths)
    size = math.ceil(len(words) / num_clips)
    script_parts = [" ".join(words[i:i+size]) for i in range(0, len(words), size)]
    
    while len(script_parts) < num_clips: script_parts.append("")

    voice_str = config.get("voice", "en-US-AndrewNeural")
    tone = config.get("tone_settings", {})
    bg_vol = float(config.get("bg_volume", 0.12))

    final_segments = []
    
    try:
        for i in range(num_clips):
            st.write(f"🎤 Synthesizing Motivational Segment {i+1}...")
            audio_p = os.path.join(TEMP_DIR, f"v_{i}.mp3")
            generate_voice_sync(script_parts[i], voice_str, tone, audio_p)

            voice_audio = AudioFileClip(audio_p).volumex(1.8) # Boost voice for clarity
            clip = VideoFileClip(video_paths[i]).without_audio() # Strip original noise
            
            # Sync video speed to match the powerful narration
            duration = voice_audio.duration
            synced_v = clip.fx(vfx.speedx, clip.duration / duration).set_duration(duration)
            
            # Add a slight cinematic fade in/out
            synced_v = synced_v.fadein(0.5).fadeout(0.5)
            
            synced_v = synced_v.set_audio(voice_audio)
            final_segments.append(synced_v)

        st.write("🎬 Assembling Final Masterpiece...")
        final_video = concatenate_videoclips(final_segments, method="compose")
        
        # Note: In a full production, you'd mix a separate music track here. 
        # For now, we are focusing on the high-impact voice and visual sync.
        final_video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")
        return True
    except Exception as e:
        st.error(f"Production Error: {e}")
        return False

# ─────────────────────────────────────────────
# STREAMLIT UI
# ─────────────────────────────────────────────
st.set_page_config(page_title="Motivational Forge", page_icon="🔥")
st.title("🔥 Motivational Video Forge")
st.markdown("Convert your ideas into **high-energy cinematic videos**.")

with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("Groq API Key", type="password")
    voice_choice = st.selectbox("Select Narrator", list(VOICE_OPTIONS.keys()))
    if st.button("Clear Cache"):
        for f in os.listdir(TEMP_DIR): os.remove(os.path.join(TEMP_DIR, f))
        st.success("Cleaned!")

col1, col2 = st.columns(2)
with col1:
    lang = st.selectbox("Language", ["English", "Urdu"])
    files = st.file_uploader("Upload Clips", type=["mp4", "mov"], accept_multiple_files=True)
with col2:
    story = st.text_area("The Concept", placeholder="Describe the struggle and the victory...")
    instr = st.text_area("Director Notes", value="Deeply motivational, cinematic pauses, high energy.")

if st.button("🚀 GENERATE MOTIVATIONAL VIDEO", use_container_width=True, type="primary"):
    if not api_key or not files or not story:
        st.error("Missing API Key, Files, or Story description!")
    else:
        with st.status("Generating Magic...") as status:
            # 1. AI Director
            plan = get_ai_production_plan(api_key, lang, story, instr, VOICE_OPTIONS[voice_choice])
            
            # 2. Process Files
            paths = []
            for i, f in enumerate(files):
                p = os.path.join(TEMP_DIR, f"raw_{i}.mp4")
                with open(p, "wb") as out: out.write(f.getbuffer())
                paths.append(p)
            
            # 3. Produce
            out_v = os.path.join(TEMP_DIR, "final.mp4")
            if produce_final_video(paths, plan['refined_script'], plan, out_v):
                status.update(label="✅ Success!", state="complete")
                st.video(out_v)
                st.download_button("Download Video", open(out_v, "rb"), "motivation.mp4")
