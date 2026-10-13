import os
import whisper

model = whisper.load_model("large")
result = model.transcribe(os.path.join(os.path.dirname(__file__), "gravacao.mp3"))

with open(os.path.join(os.path.dirname(__file__), "transcricao.txt"), "w", encoding="utf-8") as f:
    f.write(result["text"])

print("Transcrição salva em transcricao.txt!")