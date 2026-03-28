import streamlit as st
import os
import asyncio
import edge_tts
import json
import math
from groq import Groq

# --- MoviePy 2.0+ Core Imports ---
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.compositing.concatenate import concatenate_videoclips
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.audio.AudioClip import CompositeAudioClip
import moviepy.video.fx as vfx

# --- Setup ---
TEMP_DIR = "temp_output"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# --- Agentic Brain (Llama 3.1) ---
def get_ai_production_plan(api_key, language, story, instructions):
    client = Groq(api_key=api_key)
    
    system_prompt = f"""
    You are an AI Video Director. Based on the user's story and instructions, create a production plan in JSON.
    Language Context: {language}
    
    Instructions:
    1. 'refined_script': Clean the user's story into a professional narrative.
    2. 'voice': Select the best voice:
       - If Urdu: 'ur-PK-AsadNeural' (Male) or 'ur-PK-UzmaNeural' (Female).
       - If English: 'en-US-AndrewNeural' (Male) or 'en-US-AvaNeural' (Female).
    3. 'tone_settings': {{'rate': 'speed', 'pitch': 'hertz'}} (e.g., rate: '-5%', pitch: '+2Hz').
    4. 'bg_volume': Float (0.1 to 0.25).
    
    Return ONLY JSON.
    """
    
    user_input = f"Story: {story}\nDirector Instructions: {instructions}"
    
    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": user_input}],
            response_format={"type": "json_object"}
        )
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        st.error(f"AI Director Error: {e}")
        return None

# --- Audio/Video Engines ---
async def generate_voice(text, voice, settings, path):
    communicate = edge_tts.Communicate(
        text, voice, 
        rate=settings.get("rate", "-5%"), 
        pitch=settings.get("pitch", "+0Hz")
    )
    await communicate.save(path)

def produce_final_video(video_paths, script, config, output_path):
    num_clips = len(video_paths)
    words = script.split()
    size = math.ceil(len(words) / num_clips)
    script_parts = [" ".join(words[i:i + size]) for i in range(0, len(words), size)]
    
    while len(script_parts) < num_clips: script_parts.append("")
    
    final_segments = []
    
    try:
        for i in range(num_clips):
            st.write(f"🎞️ Syncing Segment {i+1} of {num_clips}...")
            audio_p = os.path.join(TEMP_DIR, f"voice_{i}.mp3")
            asyncio.run(generate_voice(script_parts[i], config['voice'], config['tone_settings'], audio_p))
            
            voice_audio = AudioFileClip(audio_p).volumex(1.6)
            clip = VideoFileClip(video_paths[i])
            
            # Match video speed to voice duration
            speed_factor = clip.duration / voice_audio.duration
            synced_v = clip.fx(vfx.multiply_speed, factor=speed_factor).set_duration(voice_audio.duration)
            
            # Preserve & Duck original music
            if clip.audio is not None:
                bg = clip.audio.volumex(config.get('bg_volume', 0.15))
                synced_v = synced_v.set_audio(CompositeAudioClip([bg, voice_audio]))
            else:
                synced_v = synced_v.set_audio(voice_audio)
                
            final_segments.append(synced_v)

        st.write("🚀 Rendering high-quality MP4...")
        final_video = concatenate_videoclips(final_segments, method="compose")
        final_video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")
        return True
    finally:
        for c in final_segments: c.close()

# --- Streamlit UI ---
st.set_page_config(page_title="Advanced AI Video Forge", layout="wide")

with st.sidebar:
    st.title("🔑 Auth & Setup")
    api_key = st.text_input("Groq API Key:", type="password")
    if st.button("🧹 Clear All Cache"):
        for f in os.listdir(TEMP_DIR):
            try: os.remove(os.path.join(TEMP_DIR, f))
            except: pass
        st.success("Cleared!")

st.title("🤖 Advanced AI Agent Video Forge")

# Step 1: Configuration
col_a, col_b = st.columns(2)
with col_a:
    language = st.selectbox("🌍 Select Language", ["Urdu", "English"])
with col_b:
    files = st.file_uploader("📹 Upload Clips (In Order)", type=["mp4", "mov"], accept_multiple_files=True)

# Step 2: Content
col_c, col_d = st.columns(2)
with col_c:
    user_story = st.text_area("📖 Put Your Story Here:", height=200, placeholder="Paste your narrative...")
with col_d:
    user_instructions = st.text_area("🎤 Director's Instructions:", height=200, 
                                     placeholder="e.g. 'Energetic male voice, fast-paced, loud background music'")

# Step 3: Production
if st.button("🔥 Generate Advanced AI Video"):
    if not api_key:
        st.error("Missing API Key in Sidebar!")
    elif not user_story or not files:
        st.warning("Please provide both a story and video clips.")
    else:
        with st.status("🛠️ AI Agent is constructing your video...") as status:
            # 1. AI Planning
            plan = get_ai_production_plan(api_key, language, user_story, user_instructions)
            
            if plan:
                st.write(f"**Persona Selected:** {plan['voice']}")
                
                # 2. Save Uploads
                paths = []
                for i, f in enumerate(files):
                    p = os.path.join(TEMP_DIR, f"raw_{i}.mp4")
                    with open(p, "wb") as out: out.write(f.getbuffer())
                    paths.append(p)
                
                # 3. Produce
                out_p = os.path.join(TEMP_DIR, "production_final.mp4")
                if produce_final_video(paths, plan['refined_script'], plan, out_p):
                    status.update(label="✅ Production Success!", state="complete")
                    st.divider()
                    st.video(out_p)
                    with open(out_p, "rb") as vid:
                        st.download_button("📥 Download MP4", vid, "AI_Video_Production.mp4")
