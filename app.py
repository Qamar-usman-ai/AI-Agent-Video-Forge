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
    
    # We use a very strict prompt to avoid the "json_validate_failed" error
    system_prompt = f"""
    You are an AI Video Director. Create a production plan in VALID JSON format.
    Language Context: {language}

    STRICT JSON STRUCTURE:
    {{
      "refined_script": "The full narrative text as a single string",
      "voice": "The voice ID string only",
      "tone_settings": {{"rate": "+0%", "pitch": "+0Hz"}},
      "bg_volume": 0.15
    }}

    VOICE GUIDELINES:
    - Urdu: Use 'ur-PK-AsadNeural' (Male) or 'ur-PK-UzmaNeural' (Female).
    - English: Use 'en-US-AndrewNeural' (Male) or 'en-US-AvaNeural' (Female).

    Do not add extra parentheses or nested objects for 'voice'.
    """
    
    user_input = f"Story: {story}\nDirector Instructions: {instructions}"
    
    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": user_input}],
            response_format={"type": "json_object"}
        )
        
        plan = json.loads(completion.choices[0].message.content)
        
        # --- SELF-HEALING LOGIC ---
        # 1. If 'voice' is a dict (common AI error), extract the ID string
        if isinstance(plan.get('voice'), dict):
            plan['voice'] = plan['voice'].get('id', 'en-US-AvaNeural')
        
        # 2. Ensure 'refined_script' is a string
        if isinstance(plan.get('refined_script'), dict):
            plan['refined_script'] = plan['refined_script'].get('text', str(plan['refined_script']))
            
        return plan
    except Exception as e:
        st.error(f"AI Director Error: {e}")
        return None

# --- Audio Engine ---
async def generate_voice(text, voice, settings, path):
    # Ensure settings is a dict
    if not isinstance(settings, dict):
        settings = {}
        
    rate = settings.get("rate", "+0%")
    pitch = settings.get("pitch", "+0Hz")
    
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(path)

# --- Video Engine ---
def produce_final_video(video_paths, script, config, output_path):
    # Safety check for script string
    if not isinstance(script, str):
        script = str(script)

    num_clips = len(video_paths)
    words = script.split()
    
    if not words:
        st.error("The script is empty. Cannot generate video.")
        return False

    size = math.ceil(len(words) / num_clips)
    script_parts = [" ".join(words[i:i + size]) for i in range(0, len(words), size)]
    
    # Ensure every clip has a part, even if it's empty
    while len(script_parts) < num_clips: 
        script_parts.append("")
    
    final_segments = []
    
    try:
        for i in range(num_clips):
            st.write(f"🎞️ Syncing Segment {i+1} of {num_clips}...")
            audio_p = os.path.join(TEMP_DIR, f"voice_{i}.mp3")
            
            # Safe extraction of config values
            voice_name = config.get('voice', 'en-US-AvaNeural')
            tone = config.get('tone_settings', {})
            
            asyncio.run(generate_voice(script_parts[i], voice_name, tone, audio_p))
            
            # MoviePy 2.x native methods for volume and speed
            voice_audio = AudioFileClip(audio_p).multiply_volume(1.6)
            clip = VideoFileClip(video_paths[i])
            
            # Calculate speed adjustment
            speed_factor = clip.duration / voice_audio.duration
            synced_v = clip.multiply_speed(speed_factor).with_duration(voice_audio.duration)
            
            if clip.audio is not None:
                bg_vol = config.get('bg_volume', 0.15)
                bg = clip.audio.multiply_volume(bg_vol)
                synced_v = synced_v.with_audio(CompositeAudioClip([bg, voice_audio]))
            else:
                synced_v = synced_v.with_audio(voice_audio)
                
            final_segments.append(synced_v)

        st.write("🚀 Rendering high-quality MP4...")
        final_video = concatenate_videoclips(final_segments, method="compose")
        final_video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")
        return True
    except Exception as e:
        st.error(f"Production Error: {e}")
        return False
    finally:
        # Resource cleanup
        for c in final_segments:
            try: c.close()
            except: pass

# --- Streamlit UI ---
st.set_page_config(page_title="Advanced AI Video Forge", layout="wide")

with st.sidebar:
    st.title("🔑 Auth & Setup")
    api_key = st.text_input("Groq API Key:", type="password")
    if st.button("🧹 Clear All Cache"):
        for f in os.listdir(TEMP_DIR):
            try: os.remove(os.path.join(TEMP_DIR, f))
            except: pass
        st.success("Cache Cleared!")

st.title("🤖 Advanced AI Agent Video Forge")

col_a, col_b = st.columns(2)
with col_a:
    language = st.selectbox("🌍 Select Language", ["Urdu", "English"])
with col_b:
    files = st.file_uploader("📹 Upload Clips (In Order)", type=["mp4", "mov"], accept_multiple_files=True)

col_c, col_d = st.columns(2)
with col_c:
    user_story = st.text_area("📖 Put Your Story Here:", height=200, placeholder="Paste your narrative...")
with col_d:
    user_instructions = st.text_area("🎤 Director's Instructions:", height=200, placeholder="e.g. 'Calm voice, low music'")

if st.button("🔥 Generate Advanced AI Video"):
    if not api_key:
        st.error("Missing API Key in Sidebar!")
    elif not user_story or not files:
        st.warning("Please provide both a story and video clips.")
    else:
        with st.status("🛠️ AI Agent is constructing your video...") as status:
            # 1. AI Planning
            plan = get_ai_production_plan(api_key, language, user_story, user_instructions)
            
            if plan and isinstance(plan, dict):
                # Use the refined script or fallback to user story
                script_to_use = plan.get('refined_script', user_story)
                
                # 2. Save Uploaded Clips
                paths = []
                for i, f in enumerate(files):
                    p = os.path.join(TEMP_DIR, f"raw_{i}.mp4")
                    with open(p, "wb") as out: out.write(f.getbuffer())
                    paths.append(p)
                
                # 3. Final Production
                out_p = os.path.join(TEMP_DIR, "production_final.mp4")
                if produce_final_video(paths, script_to_use, plan, out_p):
                    status.update(label="✅ Production Success!", state="complete")
                    st.divider()
                    st.video(out_p)
                    with open(out_p, "rb") as vid:
                        st.download_button("📥 Download MP4", vid, "AI_Video_Production.mp4")
            else:
                st.error("AI Planning failed. Try again or check your prompt.")
