from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
resp = client.post('/ask', json={'question': 'What is the leave policy?'})
print(resp.status_code)
print(resp.json().get('tts_available'))
print((resp.json().get('answer') or '')[:120])
print(resp.json().get('audio_url'))
