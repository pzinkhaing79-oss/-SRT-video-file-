import streamlit as st
import whisper
import os
import subprocess
import time
from google import genai
from google.genai import types
# ပြင်ဆင်ထားသော MoviePy Import (Error မတက်တော့ပါ)
from moviepy import VideoFileClip, AudioFileClip, concatenate_audioclips 

# --- SETUP & UI ---
st.set_page_config(page_title="Gemini 3.1 Dubber", page_icon="🎙️", layout="wide")

st.markdown("""
    <div style="background-color:#1E88E5;padding:20px;border-radius:15px;margin-bottom:25px">
    <h2 style="color:white;text-align:center;">🎙️ AI Video Dubbing (Gemini 3.1)</h2>
    </div>
    """, unsafe_allow_html=True)

# --- SIDEBAR SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    api_key = st.text_input("Gemini API Key ထည့်ပါ", type="password")
    
    st.divider()
    
    st.subheader("🗣️ အသံဆက်တင်များ")
    # အသံအမျိုးအစား ရွေးချယ်ရန်
    voice_choice = st.selectbox(
        "အသံပြောသူ ရွေးချယ်ပါ", 
        ["Puck (အမျိုးသား)", "Charon (အမျိုးသမီး)", "Kore (အမျိုးသမီး)"]
    )
    voice_name = voice_choice.split()[0] # ဥပမာ- 'Puck' ကိုပဲ ယူမည်
    
    # အသံနေအသံထား (Emotion) ရွေးချယ်ရန်
    tone_choice = st.selectbox(
        "အသံနေအသံထား (Tone/Emotion)",
        ["Natural (သဘာဝအတိုင်း)", "Scary/Dramatic (ခြောက်ခြားဖွယ်/စိတ်လှုပ်ရှားဖွယ်)", "Funny (ဟာသ)"]
    )

if api_key:
    client = genai.Client(api_key=api_key)

# --- FUNCTIONS ---

def translate_with_tags(text, tone):
    """Safety filter ပိတ်ထားပြီး Emotion အလိုက် Tag များထည့်ပေးသော Function"""
    
    # ရွေးချယ်ထားသော Tone အပေါ်မူတည်ပြီး Prompt ပြောင်းလဲခြင်း
    emotion_prompt = "appropriate tags like [laugh], [sigh], or [fast]"
    if tone == "Scary/Dramatic":
        emotion_prompt = "suspenseful tags like [whisper], [gasp], [slow], or [scared]"
    elif tone == "Funny":
        emotion_prompt = "comedic tags like [laugh], [chuckle], [exclamatory]"
        
    prompt = f"""
    Translate the following English subtitle into conversational Burmese.
    You must include Gemini TTS audio tags ({emotion_prompt}) where it fits the context.
    Output ONLY the translated Burmese text with the tags.
    Text: "{text}"
    """
    
    try:
        # Client Error မတက်စေရန် Flash model နှင့် Safety Settings များ ဖြေလျှော့ထားသည်
        response = client.models.generate_content(
            model="gemini-1.5-flash", 
            contents=prompt,
            config=types.GenerateContentConfig(
                safety_settings=[
                    {"category": "HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                    {"category": "SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                ]
            )
        )
        return response.text.strip()
    except Exception as e:
        # Error တက်ခဲ့လျှင် ပရိုဂရမ် မရပ်သွားစေရန်
        st.warning(f"Translation Error at text: '{text}'. Using original text.")
        return text 

def generate_gemini_tts(text, voice_name, filename):
    """ရွေးချယ်ထားသော Voice ဖြင့် အသံဖန်တီးခြင်း"""
    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-tts-preview",
            contents=text,
            config=types.GenerateContentConfig(
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                    )
                )
            )
        )
        with open(filename, "wb") as f:
            f.write(response.audio_bytes)
        return True
    except Exception as e:
        st.error(f"TTS Error: {str(e)}")
        return False

def sync_audio(audio_path, target_duration):
    """FFmpeg ဖြင့် အချိန်ညှိခြင်း"""
    output_path = f"synced_{audio_path}"
    cmd_duration = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {audio_path}"
    try:
        current_duration = float(subprocess.check_output(cmd_duration.split()))
        speed = max(0.5, min(2.0, current_duration / target_duration)) 
        subprocess.run(['ffmpeg', '-y', '-i', audio_path, '-filter:a', f'atempo={speed}', output_path], capture_output=True)
        return output_path
    except:
        return audio_path # Error တက်လျှင် မူရင်းဖိုင်ကိုသာ ပြန်ပေးမည်

# --- MAIN APP LOGIC ---

uploaded_file = st.file_uploader("ဗီဒီယိုဖိုင် တင်ပါ (MP4)", type=['mp4'])

if uploaded_file and api_key:
    if st.button("🚀 ဗီဒီယိုကို အသံပြောင်းမည်"):
        with st.status("လုပ်ငန်းစဉ် စတင်နေပါပြီ...", expanded=True) as status:
            
            with open("input.mp4", "wb") as f:
                f.write(uploaded_file.read())
            
            st.write("🎙️ ၁။ စာသားထုတ်ယူနေသည် (Whisper)...")
            model = whisper.load_model("base")
            result = model.transcribe("input.mp4")
            segments = result['segments']
            
            st.write(f"🗣️ ၂။ {voice_name} ၏ အသံ ({tone_choice}) ဖြင့် ဖန်တီးနေသည်...")
            final_audio_segments = []
            
            # Progress Bar ထည့်သွင်းခြင်း
            progress_bar = st.progress(0)
            total_segments = len(segments)
            
            for i, seg in enumerate(segments):
                start, end = seg['start'], seg['end']
                duration = end - start
                
                # ဘာသာပြန်ခြင်း
                myan_text = translate_with_tags(seg['text'], tone_choice)
                
                # အသံဖန်တီးခြင်း
                temp_audio = f"temp_{i}.mp3"
                success = generate_gemini_tts(myan_text, voice_name, temp_audio)
                
                if success:
                    synced_audio = sync_audio(temp_audio, duration)
                    final_audio_segments.append(AudioFileClip(synced_audio).set_start(start))
                
                # Free API Limit မကျော်စေရန် ၁ စက္ကန့် နားပေးခြင်း (အရေးကြီးသည်)
                time.sleep(1) 
                
                # Progress Update
                progress_bar.progress((i + 1) / total_segments)
            
            st.write("🎬 ၃။ ဗီဒီယို အချောသတ်နေသည် (MoviePy)...")
            video_clip = VideoFileClip("input.mp4").without_audio()
            if final_audio_segments:
                final_audio = concatenate_audioclips(final_audio_segments)
                final_video = video_clip.set_audio(final_audio)
                final_video.write_videofile("final_dubbed.mp4", codec="libx264", audio_codec="aac", logger=None)
                
                status.update(label="လုပ်ငန်းစဉ် ပြီးဆုံးပါပြီ! 🎉", state="complete")
                st.video("final_dubbed.mp4")
                st.download_button("📥 ဗီဒီယို ဒေါင်းလုဒ်ဆွဲရန်", open("final_dubbed.mp4", "rb"), "dubbed_video.mp4")
            else:
                status.update(label="အသံဖန်တီးမှု မအောင်မြင်ပါ။", state="error")
                
elif not api_key:
    st.warning("ဘေးဘက် Sidebar တွင် Gemini API Key အရင်ထည့်ပေးပါ။")
