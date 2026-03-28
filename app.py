import streamlit as st
import os
import asyncio
import edge_tts
import json
import math
from groq import Groq

# --- MoviePy 2.0+ Specialist Imports ---
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.compositing.concatenate import concatenate_videoclips
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.audio.AudioClip import CompositeAudioClip
import moviepy.video.fx as vfx

# --- Directory Setup ---
TEMP_DIR = "temp_output"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# --- AI Agent Logic (Llama 3.1) ---
def ai_director(user_prompt, api_key):
    """The LLM acts as the creative lead, deciding the script and voice settings."""
    client = Groq(api_key=api_key)
    
    system_prompt = """
    You are a Professional Video Director. Create a JSON production plan.
    - 'script': High-impact script in the user's requested language (Urdu/English).
    - 'voice': Select 'ur-PK-AsadNeural' (Urdu Male), 'ur-PK-UzmaNeural' (Urdu Female), 
               'en-US-AndrewNeural' (Eng Male), or 'en-US-AvaNeural' (Eng Female).
    - 'tone_settings': {'rate': '-5%', 'pitch': '+2Hz'} (Adjust based on mood).
    - 'bg_music_level': Float between 0.1 and 0.2 (Volume of the original clip's audio).
    
    Return ONLY JSON. No conversation.
    """
    
    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        st.error(f"LLM Error: {e}")
        return None

# --- Voice Engine ---
async def generate_voice(text, voice, settings, path):
    communicate = edge_tts.Communicate(
        text, voice, 
        rate=settings.get("rate", "-5%"), 
        pitch=settings.get("pitch", "+0Hz")
    )
    await communicate.save(path)

# --- Video Engine ---
def process_video_production(video_paths, script, config, output_path):
    num_clips = len(video_paths)
    words = script.split()
    size = math.ceil(len(words) / num_clips)
    script_parts = [" ".join(words[i:i + size]) for i in range(0, len(words), size)]
    
    # Ensure list matches clip count
    while len(script_parts) < num_clips: script_parts.append("")
    
    final_segments = []
    
    try:
        for i in range(num_clips):
            st.write(f"🎞️ Synthesizing Segment {i+1}...")
            
            # 1. Voice Generation
            audio_p = os.path.join(TEMP_DIR, f"voice_{i}.mp3")
            asyncio.run(generate_voice(script_parts[i], config['voice'], config['tone_settings'], audio_p))
            
            voice_audio = AudioFileClip(audio_p).volumex(1.6) # Main Voice
            clip = VideoFileClip(video_paths[i])
            
            # 2. Sync: Match video speed to voice duration
            speed_factor = clip.duration / voice_audio.duration
            synced_v = clip.fx(vfx.multiply_speed, factor=speed_factor).set_duration(voice_audio.duration)
            
            # 3. Audio Mixing: Preserve clip music if present
            if clip.audio is not None:
                # Duck the original music to the level suggested by AI
                original_music = clip.audio.volumex(config.get('bg_music_level', 0.15))
                synced_v = synced_v.set_audio(CompositeAudioClip([original_music, voice_audio]))
            else:
                synced_v = synced_v.set_audio(voice_audio)
                
            final_segments.append(synced_v)

        # 4. Export
        st.write("🚀 Rendering Final Masterpiece...")
        final_video = concatenate_videoclips(final_segments, method="compose")
        final_video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")
        return True
    except Exception as e:
        st.error(f"Render Error: {e}")
        return False
    finally:
        for c in final_segments: c.close()

# --- UI ---
st.set_page_config(page_title="AI Agent Forge", layout="wide")

# Sidebar for API Key
with st.sidebar:
    st.title("🔑 Authentication")
    api_key = st.text_input("Enter Groq API Key:", type="password")
    st.info("Get your key at [console.groq.com](https://console.groq.com/)")
    if st.button("🧹 Clear All Temp Files"):
        for f in os.listdir(TEMP_DIR):
            try: os.remove(os.path.join(TEMP_DIR, f))
            except: pass
        st.success("Cleared!")

st.title("🤖 AI Agent Video Forge")
st.markdown("Automate high-quality Urdu/English content creation using Llama 3.1 Agents.")

c1, c2 = st.columns(2)

with c1:
    st.subheader("📝 Production Instructions")
    prompt = st.text_area("What is the video about?", height=150, 
                          placeholder="Example: A motivational Urdu video about never giving up. Use a strong male voice.")
    
    st.subheader("📹 Source Clips")
    files = st.file_uploader("Upload Multi-Clips (MP4/MOV)", type=["mp4", "mov"], accept_multiple_files=True)

if st.button("🔥 Start Agentic Production"):
    if not api_key:
        st.error("Please enter your Groq API Key in the sidebar!")
    elif not prompt or not files:
        st.warning("Prompt and Video Clips are required.")
    else:
        with st.status("🛠️ Agent is working...") as status:
            # Plan
            plan = ai_director(prompt, api_key)
            if plan:
                st.write(f"**Director's Plan:** {plan['voice']} selected.")
                
                # Save Files
                paths = []
                for i, f in enumerate(files):
                    p = os.path.join(TEMP_DIR, f"raw_{i}.mp4")
                    with open(p, "wb") as out: out.write(f.getbuffer())
                    paths.append(p)
                
                # Render
                out_p = os.path.join(TEMP_DIR, "production_final.mp4")
                if process_video_production(paths, plan['script'], plan, out_p):
                    status.update(label="✅ Production Success!", state="complete")
                    st.divider()
                    st.video(out_p)
                    with open(out_p, "rb") as vid:
                        st.download_button("📥 Download Final Video", vid, "AI_Agent_Video.mp4")
