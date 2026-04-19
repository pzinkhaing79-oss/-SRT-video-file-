import streamlit as st
import whisper
import os
import subprocess
import datetime
from google import genai
from google.genai import types
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_audioclips

# --- SETUP ---
st.set_page_config(page_title="Gemini 3.1 AI Video Dubber", layout="wide")
st.title("🎥 Gemini 3.1 Flash TTS: Professional Video Dubbing")

# API Key ကို Sidebar တွင် ထည့်ရန် သို့မဟုတ် Environment Variable မှယူရန်
api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")
client = None
if api_key:
    client = genai.Client(api_key=api_key)

# --- FUNCTIONS ---

def translate_with_tags(text):
    """Gemini Pro ကိုသုံးပြီး Audio Tags များပါဝင်သော မြန်မာဘာသာပြန်ယူခြင်း"""
    prompt = f"""
    Translate the following English video subtitle into natural, conversational Burmese.
    IMPORTANT: Include Gemini 3.1 TTS audio tags like [laugh], [whisper], [exclamatory], [questioning], [fast], or [slow] 
    to match the original emotion. 
    Text: "{text}"
    Output ONLY the translated Burmese text with tags.
    """
    response = client.models.generate_content(model="gemini-1.5-pro", contents=prompt)
    return response.text.strip()

def generate_gemini_tts(text, voice_name, filename):
    """Gemini 3.1 Flash TTS model ကို အပြည့်အဝ အသုံးချခြင်း"""
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

def sync_audio_to_duration(audio_path, target_duration):
    """FFmpeg သုံးပြီး အသံဖိုင်ကို Video အချိန်နှင့် ကွက်တိညှိခြင်း (Time Stretching)"""
    output_path = f"synced_{audio_path}"
    # လက်ရှိ အသံဖိုင် ကြာချိန်ကို စစ်ဆေးသည်
    cmd_duration = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {audio_path}"
    current_duration = float(subprocess.check_output(cmd_duration.split()))
    
    # Speed factor တွက်ချက်ခြင်း
    speed = current_duration / target_duration
    # atempo သည် 0.5 နှင့် 2.0 ကြားပဲ ရသဖြင့် ကန့်သတ်ချက်ထားရသည်
    speed = max(0.5, min(2.0, speed)) 
    
    subprocess.run(['ffmpeg', '-y', '-i', audio_path, '-filter:a', f'atempo={speed}', output_path], capture_output=True)
    return output_path

# --- UI LOGIC ---

uploaded_file = st.file_uploader("ဗီဒီယိုဖိုင် တင်ပါ (MP4)", type=['mp4'])

if uploaded_file and client:
    if st.button("Start Dubbing"):
        with st.status("Processing...", expanded=True) as status:
            # ၁။ ဗီဒီယိုသိမ်းဆည်းခြင်း
            with open("input.mp4", "wb") as f:
                f.write(uploaded_file.read())
            
            # ၂။ Whisper ဖြင့် စာသားထုတ်ခြင်း
            st.write("🎙️ Transcription လုပ်နေသည် (Whisper)...")
            model = whisper.load_model("base")
            result = model.transcribe("input.mp4")
            segments = result['segments']
            
            # ၃။ ဘာသာပြန်ခြင်းနှင့် TTS ထုတ်ခြင်း
            st.write("🗣️ Gemini 3.1 ဖြင့် ဘာသာပြန်ပြီး အသံဖန်တီးနေသည်...")
            final_audio_segments = []
            srt_content = ""
            
            for i, seg in enumerate(segments):
                start, end = seg['start'], seg['end']
                duration = end - start
                
                # ဘာသာပြန် (Audio Tags ပါဝင်ပြီးသား)
                myan_text = translate_with_tags(seg['text'])
                srt_content += f"{i+1}\n{start} --> {end}\n{myan_text}\n\n"
                
                # TTS ထုတ်ယူခြင်း
                temp_audio = f"temp_{i}.mp3"
                generate_gemini_tts(myan_text, "Puck", temp_audio)
                
                # အချိန်ညှိခြင်း
                synced_audio = sync_audio_to_duration(temp_audio, duration)
                final_audio_segments.append(AudioFileClip(synced_audio).set_start(start))
            
            # ၄။ SRT ဖိုင်ထုတ်ပေးခြင်း
            with open("output.srt", "w", encoding="utf-8") as f:
                f.write(srt_content)
            
            # ၅။ Video နှင့် အသံအသစ် ပေါင်းစပ်ခြင်း
            st.write("🎬 ဗီဒီယို အချောသတ်နေသည်...")
            video_clip = VideoFileClip("input.mp4").without_audio()
            final_audio = concatenate_audioclips(final_audio_segments)
            final_video = video_clip.set_audio(final_audio)
            final_video.write_videofile("final_dubbed.mp4", codec="libx264", audio_codec="aac")
            
            status.update(label="လုပ်ငန်းစဉ် ပြီးဆုံးပါပြီ!", state="complete")
        
        # Download Buttons
        st.video("final_dubbed.mp4")
        st.download_button("Download Dubbed Video", open("final_dubbed.mp4", "rb"), "dubbed_video.mp4")
        st.download_button("Download SRT File", srt_content, "subtitle.srt")

elif not api_key:
    st.warning("Please enter your Gemini API Key in the sidebar.")
