
from dotenv import load_dotenv
from gnani.stt import GnaniSTTClient

load_dotenv()

def transcribe_audio(audio_bytes, filename, language_code):
    client = GnaniSTTClient()

    result = client.transcribe_bytes(
        audio_bytes,
        filename=filename,
        language_code=language_code,
        model="prisma-v3.0",
        format="transcribe"
    )

    return (
        result.get("transcript", ""),
        result.get("detected_language_code")
    )
