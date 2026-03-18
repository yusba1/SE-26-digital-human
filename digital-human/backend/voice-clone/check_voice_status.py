#!/usr/bin/env python3
"""
Check voice clone status using DashScope VoiceEnrollmentService
"""
import os
import sys
from dashscope.audio.tts_v2 import VoiceEnrollmentService


def check_voice_status(voice_id=None, prefix=None):
    """Check voice clone status by voice_id or prefix"""
    # Set API Key
    api_key = os.getenv('DASHSCOPE_API_KEY', 'sk-de14e27f332543f1835d1080dccf36fd')
    
    # Initialize service
    service = VoiceEnrollmentService()
    
    # Set API key
    import dashscope
    dashscope.api_key = api_key
    
    try:
        # Query voice list
        if prefix:
            print(f"Querying voices with prefix: {prefix}")
            voices = service.list_voices(prefix=prefix, page_index=0, page_size=100)
        else:
            print("Querying all voices...")
            voices = service.list_voices(page_index=0, page_size=100)
        
        request_id = service.get_last_request_id()
        print(f"Request ID: {request_id}\n")
        
        if not voices:
            print("No voices found.")
            return None
        
        # Filter by voice_id if provided
        if voice_id:
            matching_voices = [v for v in voices if v.get('voice_id') == voice_id]
            if not matching_voices:
                print(f"Voice ID '{voice_id}' not found.")
                print(f"\nAvailable voices ({len(voices)}):")
                for voice in voices:
                    print(f"  - {voice.get('voice_id')}") 
                    print(f"    Status: {voice.get('status')}")
                return None
            voices = matching_voices
        
        # Display results
        print(f"Found {len(voices)} voice(s):\n")
        for voice in voices:
            print(f"Voice ID: {voice.get('voice_id')}")
            print(f"Status: {voice.get('status')}")
            print(f"Created: {voice.get('gmt_create')}")
            print(f"Modified: {voice.get('gmt_modified')}")
            
            status = voice.get('status')
            if status == 'OK':
                print("✓ Status: Ready to use!")
            elif status == 'DEPLOYING':
                print("⏳ Status: Under review...")
            elif status == 'UNDEPLOYED':
                print("✗ Status: Review failed, cannot be used")
            print()
        
        return voices
        
    except Exception as e:
        print(f"Error checking voice status: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    # Check specific voice ID from previous clone
    voice_id = 'cosyvoice-v3-plus-leijun-d597c317ef6f4fc1ad534e40ca53378d'
    
    # Allow command line argument
    if len(sys.argv) > 1:
        voice_id = sys.argv[1]
    
    # Or check by prefix
    prefix = None
    if len(sys.argv) > 2 and sys.argv[1] == '--prefix':
        prefix = sys.argv[2]
        voice_id = None
    
    check_voice_status(voice_id=voice_id, prefix=prefix)
