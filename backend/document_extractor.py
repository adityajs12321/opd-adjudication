from google import genai
from google.genai import types

def extract_document(client: genai.Client, file_bytes: bytes, mime_type: str, prompt: str, schema_class):
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        return schema_class.model_validate_json(response.text)
    except Exception:
        return schema_class()