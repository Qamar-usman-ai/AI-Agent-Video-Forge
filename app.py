import streamlit as st
import os
import asyncio
import edge_tts
import json
import math
from groq import Groq

# --- Corrected Imports for MoviePy 2.0+ ---
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.compositing.concatenate import concatenate_videoclips
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.audio.AudioClip import CompositeAudioClip
import moviepy.video.fx as vfx

# --- Initialization ---
# Ensure your GROQ_API_KEY is in Streamlit Secrets
try:
    client = Groq(api_key=st.secrets["GROQ_API_KEY"])
except Exception as e:
    st.error("GROQ_API_KEY not found in secrets!")

TEMP_DIR = "temp_output"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# --- Agentic Director (Llama 3.1) ---
def ai_director(user_prompt):
    """Uses Llama 3.1 to act as a Director and Scriptwriter."""
    system_prompt = """
    You are an expert Video Director and Scriptwriter. 
    Based on the user's prompt, generate a JSON response with:
    1. 'script': A high-quality motivational script (in Urdu or English as requested).
    2. 'voice': Choose exactly one: 'ur-PK-AsadNeural', 'ur-PK-UzmaNeural', 'en-US-AndrewNeural', 'en-US-AvaNeural'.
    3. 'tone_settings': A dictionary with 'rate' (e.g., '-5%') and 'pitch' (e.g., '+5Hz').
    4. 'bg_volume': A float between 0.05 and 0.2 for background music ducking.
    
    Return ONLY a valid JSON object. Do not include markdown formatting or extra text.
    """
    
    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        st.error(f"AI Director Error: {e}")
        return None

# --- Voice Generation ---
async def generate_voice(text, voice, settings, path):
    """Generates AI Voice using Edge-TTS."""
    communicate = edge_tts.Communicate(
        text, 
        voice, 
        rate=settings.get("rate", "-5%"), 
        pitch=settings.get("pitch", "+0Hz")
    )
    await communicate.save(path)

# --- Video Production Engine ---
def build_video(video_paths, script, config, output_path):
    """Core engine to sync AI voice with video clips."""
    num_clips = len(video_paths)
    words = script.split()
    
    # Logic to split script among available clips
    size = math.ceil(len(words) / num_clips)
    script_parts = [" ".join(words[i:i + size]) for i in range(0, len(words), size)]
    
    # Ensure script_parts length matches num_clips
    while len(script_parts) < num_clips:
        script_parts.append("")
    
    final_segments = []
    
    try:
        for i in range(num_clips):
            st.write(f"🎬 Processing Segment {i+1}...")
            
            # 1. Generate Voice segment
            seg_audio_path = os.path.join(TEMP_DIR, f"audio_{i}.mp3")
            asyncio.run(generate_voice(script_parts[i], config['voice'], config['tone_settings'], seg_audio_path))
            
            # 2. Load Clips
            ai_voice = AudioFileClip(seg_audio_path).volumex(1.5)
            clip = VideoFileClip(video_paths[i])
            
            # 3. Time-Sync (Multiply Speed)
            # Factor = Original Duration / Target Voice Duration
            speed_factor = clip.duration / ai_voice.duration
            synced_clip = clip.fx(vfx.multiply_speed, factor=speed_factor).set_duration(ai_voice.duration)
            
            # 4. Audio Mixing
            if clip.audio is not None:
                bg_music = clip.audio.volumex(config.get('bg_volume', 0.15))
                combined_audio = CompositeAudioClip([bg_music, ai_voice])
            else:
                combined_audio = ai_voice
                
            synced_clip = synced_clip.set_audio(combined_audio)
            final_segments.append(synced_clip)

        # 5. Concatenate and Export
        st.write("🎞️ Finalizing Render...")
        final_video = concatenate_videoclips(final_segments, method="compose")
        final_video.write_videofile(
            output_path, 
            fps=24, 
            codec="libx264", 
            audio_codec="aac",
            temp_audiofile=os.path.join(TEMP_DIR, "temp-audio.m4a"),
            remove_temp=True
        )
        return True
        
    except Exception as e:
        st.error(f"Production Error: {e}")
        return False
    finally:
        # Cleanup clips to release memory
        for c in final_segments:
            c.close()
        if 'final_video' in locals():
            final_video.close()

# --- Streamlit Interface ---
st.set_page_config(page_title="AI Agent Video Forge", page_icon="🤖", layout="wide")

st.title("🤖 AI Agent Video Forge: Llama 3.1 Edition")
st.markdown("Describe your video idea, upload clips, and let the AI Agent handle the script, voice selection, and editing.")

with st.sidebar:
    st.header("⚙️ Control Panel")
    if st.button("🧹 Clear Workspace"):
        for f in os.listdir(TEMP_DIR):
            try: os.remove(os.path.join(TEMP_DIR, f))
            except: pass
        st.success("Workspace cleared!")
    st.info("Agent uses Llama-3.1-8b-instant for decision making.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Director's Brief")
    user_prompt = st.text_area(
        "Describe your video (Topic, Language, Mood):",
        height=200,
        placeholder="e.g., Create a 30-second motivational video in Urdu about consistency. Use an energetic male voice."
    )
    
    st.subheader("2. Source Materials")
    uploaded_files = st.file_uploader("Upload 3-6 Video Clips", type=["mp4", "mov"], accept_multiple_files=True)

with col2:
    st.subheader("3. Production Status")
    if st.button("🚀 Start AI Production"):
        if not user_prompt or not uploaded_files:
            st.warning("Please provide both a prompt and video clips.")
        else:
            with st.status("🧠 Agent is planning production...") as status:
                # Step 1: AI Planning
                config = ai_director(user_prompt)
                
                if config:
                    st.write(f"**Voice Selected:** {config['voice']}")
                    st.write(f"**Script Preview:** {config['script'][:150]}...")
                    
                    # Step 2: Save Raw Files
                    paths = []
                    for i, f in enumerate(uploaded_files):
                        p = os.path.join(TEMP_DIR, f"raw_{i}.mp4")
                        with open(p, "wb") as out:
                            out.write(f.getbuffer())
                        paths.append(p)
                    
                    # Step 3: Run Video Engine
                    output_v = os.path.join(TEMP_DIR, "final_production.mp4")
                    success = build_video(paths, config['script'], config, output_v)
                    
                    if success:
                        status.update(label="✅ Production Complete!", state="complete")
                        st.video(output_v)
                        with open(output_v, "rb") as vid_file:
                            st.download_button("📥 Download Final Video", vid_file, "AI_Agent_Production.mp4")
                    else:
                        status.update(label="❌ Production Failed", state="error")
