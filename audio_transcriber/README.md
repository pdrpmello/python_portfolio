# Audio Transcriber

Transcreve um arquivo de áudio para texto com o
[Whisper](https://github.com/openai/whisper), da OpenAI, rodando localmente.
O áudio não sai da sua máquina.

## Requisitos

- Python e as dependências de `requirements.txt`
- [ffmpeg](https://ffmpeg.org/) no PATH (o Whisper usa para ler o áudio)

## Uso

1. Coloque o áudio nesta pasta com o nome `gravacao.mp3`.
2. Rode:

   ```bash
   pip install -r requirements.txt
   python audio_transcriber.py
   ```

3. A transcrição sai em `transcricao.txt`, nesta mesma pasta.

O script usa o modelo `large`, o mais preciso e também o mais pesado: são cerca
de 3 GB de download no primeiro uso, e ele roda bem mais rápido com GPU. Para
testes rápidos, troque por `"small"` ou `"medium"` em `whisper.load_model`.

Os áudios e as transcrições estão no `.gitignore`, então não vão para o repositório.
