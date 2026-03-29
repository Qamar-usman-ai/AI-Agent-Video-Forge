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
    3. 'tone_settings': {{"rate": "+0%", "pitch": "+0Hz"}} 
    4. 'bg_volume': Float (0.1 to 0.25).
    
    Return ONLY valid JSON. No conversational text.
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
    # Fallback for settings if they are missing
    rate = settings.get("rate", "+0%") if settings else "+0%"
    pitch = settings.get("pitch", "+0Hz") if settings else "+0Hz"
    
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
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
            
            # Extract config safely to avoid AttributeErrors
            voice_name = config.get('voice', 'en-US-AvaNeural')
            tone = config.get('tone_settings', {})
            
            asyncio.run(generate_voice(script_parts[i], voice_name, tone, audio_p))
            
            voice_audio = AudioFileClip(audio_p).with_volume_scaled(1.6)
            clip = VideoFileClip(video_paths[i])
            
            # Match video speed to voice duration
            speed_factor = clip.duration / voice_audio.duration
            # MoviePy 2.0+ uses with_effects for fx
            synced_v = clip.with_effects([vfx.MultiplySpeed(speed_factor)]).with_duration(voice_audio.duration)
            
            # Preserve & Duck original music
            if clip.audio is not None:
                bg_vol = config.get('bg_volume', 0.15)
                bg = clip.audio.with_volume_scaled(bg_vol)
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
        for c in final_segments: 
            try: c.close()
            except: pass

# --- Streamlit UI ---
st.set_page_config(page_title="Advanced AI Video Forge", layout="wide")

with st.sidebar:
    st.title("🔑 Auth & Setup")
    api_key = st.text_input("Groq API Key:", type="password")
    if st.button("清理 Cache (Clear All)"):
        for f in os.listdir(TEMP_DIR):
            try: os.remove(os.path.join(TEMP_DIR, f))
            except: pass
        st.success("Cleared!")

st.title("🤖 Advanced AI Agent Video Forge")

col_a, col_b = st.columns(2)
with col_a:
    language = st.selectbox("🌍 Select Language", ["Urdu", "English"])
with col_b:
    files = st.file_uploader("📹 Upload Clips (In Order)", type=["mp4", "mov"], accept_multiple_files=True)

col_c, col_d = st.columns(2)
with col_c:
    user_story = st.text_area("📖 Put Your Story Here:", height=200)
with col_d:
    user_instructions = st.text_area("🎤 Director's Instructions:", height=200)

if st.button("🔥 Generate Advanced AI Video"):
    if not api_key:
        st.error("Missing API Key!")
    elif not user_story or not files:
        st.warning("Provide story and clips.")
    else:
        with st.status("🛠️ AI Agent working...") as status:
            plan = get_ai_production_plan(api_key, language, user_story, user_instructions)
            
            if plan and isinstance(plan, dict):
                # Ensure keys exist even if AI missed them
                script = plan.get('refined_script', user_story)
                
                paths = []
                for i, f in enumerate(files):
                    p = os.path.join(TEMP_DIR, f"raw_{i}.mp4")
                    with open(p, "wb") as out: out.write(f.getbuffer())
                    paths.append(p)
                
                out_p = os.path.join(TEMP_DIR, "production_final.mp4")
                
                if produce_final_video(paths, script, plan, out_p):
                    status.update(label="✅ Success!", state="complete")
                    st.video(out_p)
                    with open(out_p, "rb") as vid:
                        st.download_button("📥 Download MP4", vid, "AI_Video.mp4")
            else:
                st.error("AI Plan failed. Check API key or Story format.")
