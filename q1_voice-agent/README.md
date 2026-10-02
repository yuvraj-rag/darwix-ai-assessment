# Q1 — Knowledge-Grounded Voice Agent

A small voice assistant prototype for **business-loan qualification**.

The assistant can:

- Listen to the user through the browser microphone
- Convert speech to text using Whisper
- Answer questions using the Q2 knowledge base
- Generate grounded answers using Qwen
- Speak the answer back using Piper TTS
- Start a simple business-loan qualification flow
- Handle requests to speak to a human
- Show the knowledge sources used for an answer
- Show basic response timing

This is a demo/prototype built for the assignment, not a production call-center system.

---

## 1. How it works

The basic flow is:

```text
Browser microphone
        ↓
Whisper STT
        ↓
Conversation / qualification logic
        ↓
Q2 Knowledge Base API
        ↓
Qwen 2.5 3B
        ↓
Piper TTS
        ↓
Browser audio
```

The important part is that the assistant does **not** keep all business policies and FAQs inside its prompt.

For knowledge questions, it asks the Q2 knowledge base for relevant information first and then gives that information to the language model.

---

# 2. Requirements

You need:

- Python 3.10+
- A working Q2 knowledge-base service
- Ollama
- Qwen 2.5 3B
- Piper TTS
- A microphone
- A modern browser such as Chrome or Edge

The project was tested locally on Windows.

---

# 3. Setup

It is recommended to use a Python virtual environment.

From the Q1 folder:

```bash
python -m venv venv
```

Activate it on Windows:

```bash
venv\Scripts\activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

---

# 4. Install and prepare Ollama

Install Ollama if it is not already installed.

Then download the model:

```bash
ollama pull qwen2.5:3b
```

Make sure Ollama is running.

You can check it with:

```bash
ollama list
```

You should see:

```text
qwen2.5:3b
```

The application expects Ollama at:

```text
http://localhost:11434
```

---

# 5. Set up Piper TTS

Install Piper:

```bash
pip install piper-tts
```

Download the voice used by this project:

```bash
python -m piper.download_voices en_US-lessac-medium
```

The application uses:

```text
en_US-lessac-medium.onnx
```

Make sure the model is available where Piper can find it.

---

# 6. Start the Q2 knowledge base

Q1 depends on Q2 for knowledge retrieval.

Open a separate terminal and go to:

```text
q2_knowledge-base/
```

Activate its virtual environment and start the API:

```bash
uvicorn app.api:app --reload --port 8000
```

Q2 should now be available at:

```text
http://localhost:8000
```

You can check:

```text
http://localhost:8000/health
```

It should return:

```json
{
  "status": "ok"
}
```

**Q2 must be running before using Q1 knowledge-grounded questions.**

---

# 7. Start Q1

Open another terminal.

Go to:

```text
q1_voice-agent/
```

Activate the Q1 virtual environment:

```bash
venv\Scripts\activate
```

Then start the application:

```bash
uvicorn app.main:app --reload --port 8001
```

Open:

```text
http://localhost:8001
```

You should see the Northstar Voice Assistant interface.

---

# 8. Using the voice interface

## Voice input

1. Click **Start Recording**
2. Speak your question
3. Click **Stop Recording**
4. Wait for transcription
5. The assistant processes the question
6. The answer is displayed and spoken back

The browser will ask for microphone permission the first time.

Allow microphone access.

---

## Text input

You can also test the assistant without using the microphone.

Enter a question in:

```text
Or Ask by Text
```

and click **Ask**.

This is useful when testing the knowledge base or conversation logic without waiting for speech transcription.

---

# 9. Example questions

### Knowledge-base question

Try:

```text
What is the leave policy?
```

The system should retrieve information from Q2 and answer using the available knowledge.

The UI also shows the sources used.

---

### Unsupported question

Ask something that is not covered by the knowledge base.

The assistant should say that it does not have enough information rather than making up an answer.

This is an important part of the design.

---

### Business-loan qualification

Try:

```text
I want a business loan.
```

The assistant starts the qualification flow and asks:

```text
How much funding are you looking for?
```

It then asks for other basic information such as:

- Business type
- Business age
- Loan purpose

The qualification panel only appears when the loan qualification flow is active.

---

### Human assistance

Try:

```text
I want to talk to a human.
```

The assistant responds with a human-escalation message.

For this prototype, the escalation is simulated rather than connected to a real CRM or call-center system.

---

# 10. Test scenarios

The assignment asks for several different conversation situations.

The following scenarios can be used for testing.

| Scenario | Example | Expected result |
|---|---|---|
| Cooperative customer | "I want a business loan." | Qualification starts |
| Objection | "I'm not sure I want to apply." | Assistant responds without inventing policy |
| Incomplete information | "I need some funding." | Assistant asks for the missing information |
| Conflicting / unclear details | Give unclear loan details | Assistant should ask for clarification |
| Out-of-scope question | Ask about something not in the KB | Safe "information unavailable" response |
| Human assistance | "Can I talk to a human?" | Escalation response |

For the final submission, record a few of these interactions and keep their transcripts/results as evidence.

---

# 11. What the interface shows

The interface provides a few useful pieces of information after each request.

### Transcript

What Whisper understood from the user's speech.

### Answer

The assistant's response.

### Knowledge Sources

The Q2 records used to answer the question.

### Latency

Basic timing for:

- Speech-to-text
- Knowledge retrieval
- LLM response
- Total processing time

This makes it easier to see where the response time is being spent.

---

# 12. Project structure

```text
q1_voice-agent/
│
├── app/
│   ├── agent.py
│   ├── conversation.py
│   ├── llm.py
│   ├── retrieval.py
│   ├── stt.py
│   ├── tts.py
│   ├── main.py
│   └── ...
│
├── frontend/
│   └── index.html
│
├── requirements.txt
└── README.md
```

### Main files

`main.py`  
Runs the FastAPI application and provides the browser/API endpoints.

`agent.py`  
Connects the main pieces together: conversation logic, retrieval, and LLM response generation.

`conversation.py`  
Contains the small amount of business-loan qualification and escalation logic.

`retrieval.py`  
Connects Q1 to the Q2 knowledge base.

`llm.py`  
Sends the retrieved information to Qwen through Ollama.

`stt.py`  
Uses Faster-Whisper for speech-to-text.

`tts.py`  
Uses Piper to convert the assistant's answer into speech.

`frontend/index.html`  
Provides the browser interface and microphone controls.

---

# 13. Important design choice: grounded answers

The assistant is instructed to answer knowledge questions using the information retrieved from Q2.

The basic idea is:

```text
User question
      ↓
Q2 retrieves relevant information
      ↓
Retrieved information + question
      ↓
Qwen
      ↓
Answer
```

If the knowledge base does not provide enough information, the assistant uses a safe fallback instead of pretending to know the answer.

This helps reduce made-up answers.

---

# 14. Current limitations

This is intentionally a small assignment prototype.

It does **not** currently include:

- Real phone/SIP calling
- A real CRM
- User authentication
- Database storage
- WebSocket streaming
- Real-time streaming transcription
- Automatic lead creation
- Real human-agent routing
- Production monitoring
- Multi-user session management

The human escalation and qualification flow are therefore demonstrated locally.

The qualification fields are also intentionally simple. The current prototype focuses on demonstrating the conversation flow rather than building a complete loan-application system.

---

# 15. Troubleshooting

### Q1 cannot retrieve information

Make sure Q2 is running:

```bash
cd q2_knowledge-base
venv\Scripts\activate
uvicorn app.api:app --reload --port 8000
```

Then check:

```text
http://localhost:8000/health
```

---

### Ollama error

Make sure Ollama is running and the model exists:

```bash
ollama list
```

Look for:

```text
qwen2.5:3b
```

---

### Microphone does not work

Check that:

- The browser has microphone permission
- Another application is not blocking the microphone
- You are opening Q1 through the local web server

---

### Piper does not generate audio

Make sure Piper is installed:

```bash
piper --help
```

and that the voice model has been downloaded:

```bash
python -m piper.download_voices en_US-lessac-medium
```

---

### Whisper is slow

The current setup uses the Medium Whisper model on CPU with:

```text
int8
beam_size=1
VAD filtering
```

This gives better transcription quality than very small models, but CPU transcription can still take some time.

For this assignment, the focus is on getting a reliable end-to-end voice demo rather than real-time production streaming.

---

# 16. Quick start

If everything is already installed, the normal workflow is just:

### Terminal 1 — Q2

```bash
cd q2_knowledge-base
venv\Scripts\activate
uvicorn app.api:app --reload --port 8000
```

### Terminal 2 — Q1

```bash
cd q1_voice-agent
venv\Scripts\activate
uvicorn app.main:app --reload --port 8001
```

Make sure Ollama is running in the background.

Then open:

```text
http://localhost:8001
```

That's it.