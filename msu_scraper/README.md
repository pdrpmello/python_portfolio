# MSU Scraper

Coleta o menor preço de NFTs, FTs e personagens no marketplace do
[MapleStory Universe](https://msu.io) e salva tudo numa planilha do Google
Sheets, com uma linha por execução.

## Como funciona

1. Abre o Chrome com um perfil dedicado e desbloqueia a MetaMask.
2. Conecta a carteira ao msu.io. Se ela já estiver conectada, pula esta etapa.
3. Busca o menor preço de cada item de `NFT_NAMES` e `FT_NAMES` e de cada
   classe de `CHARACTER_JOBS`.
4. Salva os preços dos itens na primeira aba da planilha e os dos personagens
   na aba `Classes`, sempre com a data do dia.

## Requisitos

- Python 3.10+
- Google Chrome com a extensão MetaMask instalada num perfil dedicado
- Uma service account do Google com acesso de **Editor** à planilha

## Instalação

```bash
cd msu_scraper
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configuração

1. Copie `config_example.py` para `config.py` e preencha os valores.
   O `config.py` está no `.gitignore`, então seus segredos não vão para o repositório.

   | Variável | O que é |
   |---|---|
   | `CHROME_USER_DATA_DIR`, `CHROME_PROFILE_DIR` | Perfil do Chrome onde está a MetaMask |
   | `METAMASK_EXTENSION_URL` | `chrome-extension://<id-da-extensão>/notification.html` |
   | `METAMASK_PASSWORD` | Senha que desbloqueia a MetaMask |
   | `SPREADSHEET_ID` | ID da planilha (o trecho entre `/d/` e `/edit` na URL) |
   | `NFT_NAMES`, `FT_NAMES`, `FT_ITEMS` | Itens monitorados e o ID de cada FT |
   | `CHARACTER_JOBS`, `SUBJOB_TO_SHEET` | Classes monitoradas e a coluna de cada uma na aba `Classes` |

2. Google Sheets:
   1. Em [console.cloud.google.com](https://console.cloud.google.com), crie um
      projeto e ative a **Google Sheets API**.
   2. Crie uma **service account**, gere uma chave JSON e salve-a como
      `msu_scraper/credentials.json`. Esse arquivo também está no `.gitignore`.
   3. Compartilhe a planilha com o e-mail da service account, com permissão de **Editor**.

## Uso

```bash
python main.py
```

No Windows, o `run_scraper.bat` faz o mesmo com o Python do `.venv` da pasta.
É o jeito mais fácil de agendar a coleta no Agendador de Tarefas.

## Estrutura

```
msu_scraper/
├── main.py              # Ponto de entrada
├── scraper.py           # Automação com Selenium e gravação via gspread
├── config_example.py    # Modelo de configuração (copie para config.py)
├── run_scraper.bat      # Atalho para Windows
├── FT_test.py           # Teste isolado da coleta de FTs
├── xpath_tester.py      # Teste de XPaths na página de personagens
├── spreadsheet_test.py  # Lista as abas de uma planilha (usa SPREADSHEET_ID_CLASSES)
└── requirements.txt
```
