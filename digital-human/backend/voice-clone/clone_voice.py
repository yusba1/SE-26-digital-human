#!/usr/bin/env python3
"""
Voice cloning script using DashScope VoiceEnrollmentService
"""
import os
import sys
from dashscope.audio.tts_v2 import VoiceEnrollmentService


def clone_voice():
    """Clone voice from audio URL and return voice ID"""
    # Set API Key
    api_key = os.getenv('DASHSCOPE_API_KEY', 'sk-de14e27f332543f1835d1080dccf36fd')
    
    # Audio URL to clone
    audio_url = 'https://xuniversity.oss-cn-hangzhou.aliyuncs.com/leijun.mp3'
    
    # Initialize service
    service = VoiceEnrollmentService()
    
    # Set API key
    import dashscope
    dashscope.api_key = api_key
    
    print(f"Creating voice clone from: {audio_url}")
    print("This may take a few moments...")
    
    try:
        # Create voice clone
        # Using cosyvoice-v3-plus as recommended in docs
        # prefix: leijun (雷军) - 6 characters, valid
        voice_id = service.create_voice(
            target_model='cosyvoice-v3-plus',
            prefix='leijun',
            url=audio_url,
            language_hints=['zh']  # Chinese audio
        )
        
        request_id = service.get_last_request_id()
        print(f"\nRequest ID: {request_id}")
        print(f"Voice ID: {voice_id}")
        
        # Query voice list to get full details
        print("\nQuerying voice list...")
        voices = service.list_voices(prefix='leijun', page_index=0, page_size=10)
        
        if voices:
            print(f"\nFound {len(voices)} voice(s):")
            for voice in voices:
                print(f"  Voice ID: {voice.get('voice_id')}")
                print(f"  Status: {voice.get('status')}")
                print(f"  Created: {voice.get('gmt_create')}")
                print(f"  Modified: {voice.get('gmt_modified')}")
                print()
        else:
            print("No voices found in list")
        
        return voice_id
        
    except Exception as e:
        print(f"Error creating voice clone: {e}")
        sys.exit(1)


if __name__ == '__main__':
    voice_id = clone_voice()
    print(f"\n=== Final Voice ID ===")
    print(voice_id)
