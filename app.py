import streamlit as st
import os
import asyncio
import edge_tts
import json
from groq import Groq
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip
import moviepy.video.fx as vfx

# Initialize Groq Client
# Tip: Put your API Key in Streamlit Secrets or .env
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

TEMP_DIR = "temp_output"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# --- Agentic Director Function ---
def ai_director(user_prompt):
    """Llama 3.1 acts as the director to plan the video."""
    system_prompt = """
    You are an expert Video Director. Based on the user's prompt, generate a JSON response.
    1. 'script': A high-quality script in the requested language (Urdu or English).
    2. 'voice': Select 'ur-PK-AsadNeural' (Male Urdu), 'ur-PK-UzmaNeural' (Female Urdu), 
       'en-US-AndrewNeural' (Male English), or 'en-US-AvaNeural' (Female English).
    3. 'tone_settings': Pitch and Rate based on the mood (e.g., '+10Hz' for excited).
    4. 'bg_volume': Float (0.1 to 0.3) for background music.
    
    Output ONLY valid JSON.
    """
    
    completion = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(completion.choices[0].message.content)

# --- Updated Voice Engine ---
async def generate_voice(text, voice, settings, path):
    communicate = edge_tts.Communicate(
        text, 
        voice, 
        rate=settings.get("rate", "-5%"), 
        pitch=settings.get("pitch", "+0Hz")
    )
    await communicate.save(path)

# --- Video Engine (MoviePy 2.0 Compatibility) ---
def build_video(video_paths, script, config, output_path):
    # Logic to split script based on number of clips
    words = script.split()
    n = len(video_paths)
    size = max(1, len(words) // n)
    script_parts = [" ".join(words[i:i + size]) for i in range(0, len(words), size)]

    final_segments = []
    
    for i in range(n):
        st.write(f"🎬 Director processing segment {i+1}...")
        seg_audio = os.path.join(TEMP_DIR, f"seg_{i}.mp3")
        
        # 1. Generate Voice with AI-selected persona
        asyncio.run(generate_voice(script_parts[i], config['voice'], config['tone_settings'], seg_audio))
        
        voice_clip = AudioFileClip(seg_audio)
        video_clip = VideoFileClip(video_paths[i])
        
        # 2. Advanced Sync: Speed adjustment
        speed_factor = video_clip.duration / voice_clip.duration
        synced_v = video_clip.fx(vfx.multiply_speed, speed_factor).set_duration(voice_clip.duration)
        
        # 3. Audio Ducking with AI-selected volume
        if video_clip.audio:
            bg = video_clip.audio.volumex(config['bg_volume'])
            synced_v = synced_v.set_audio(CompositeAudioClip([bg, voice_clip]))
        else:
            synced_v = synced_v.set_audio(voice_clip)
            
        final_segments.append(synced_v)

    final_video = concatenate_videoclips(final_segments, method="compose")
    final_video.write_videofile(output_path, fps=24, codec="libx264")
    
    # Cleanup
    final_video.close()
    for s in final_segments: s.close()

# --- Streamlit UI ---
st.title("🤖 AI Agent Video Forge")

user_instruction = st.text_area("What is your video about?", 
                               placeholder="e.g. Write an Urdu script about success. Use an energetic male voice.")

uploaded_files = st.file_uploader("Upload Visuals", type=["mp4"], accept_multiple_files=True)

if st.button("🚀 Agent: Create Video"):
    if user_instruction and uploaded_files:
        with st.status("🧠 Agent is thinking...") as status:
            # Step 1: LLM Planning
            config = ai_director(user_instruction)
            st.write(f"**Director's Plan:** {config['voice']} selected.")
            st.info(f"**Script:** {config['script'][:100]}...")
            
            # Step 2: File Handling
            paths = []
            for i, f in enumerate(uploaded_files):
                p = os.path.join(TEMP_DIR, f"input_{i}.mp4")
                with open(p, "wb") as out: out.write(f.getbuffer())
                paths.append(p)
            
            # Step 3: Production
            out_file = os.path.join(TEMP_DIR, "agent_output.mp4")
            build_video(paths, config['script'], config, out_file)
            
            status.update(label="✅ Production Complete!", state="complete")
        
        st.video(out_file)
    else:
        st.error("Need instructions and videos!")
