# MSU Scraper

Automação de coleta de preços de NFTs no marketplace do MapleStory Universe (msu.io), com salvamento automático no Google Sheets.

## Funcionalidades

- Conexão automática com a carteira MetaMask
- Coleta do menor preço de cada NFT configurado
- Salvamento automático em planilha Google Sheets com data de registro
- Detecção automática de carteira já conectada

## Requisitos

- Python 3.10+
- Google Chrome instalado
- Extensão MetaMask instalada no Chrome

## Instalação

```bash
pip install -r requirements.txt
```

## Configuração

Crie um arquivo `config.py` na raiz do projeto com as seguintes variáveis:

```python
CHROME_USER_DATA_DIR = "caminho/para/seu/perfil/chrome"
CHROME_PROFILE_DIR   = "Default"
MAPLESTORY_BASE      = "https://msu.io"
MARKETPLACE_NFT_BASE = "https://msu.io/marketplace/nft"
METAMASK_EXTENSION_URL = "chrome-extension://<id-da-sua-metamask>/notification.html"
METAMASK_PASSWORD    = "sua_senha_metamask"
SPREADSHEET_ID       = "id_da_sua_planilha_google_sheets"
```

### Google Sheets

1. Acesse [console.cloud.google.com](https://console.cloud.google.com)
2. Crie um projeto e ative a **Google Sheets API**
3. Crie uma **Conta de Serviço** e baixe o JSON como `credentials.json`
4. Compartilhe a planilha com o e-mail da conta de serviço com permissão de **Editor**

## Uso

```bash
python main.py
```

Na primeira execução o script irá:
1. Desbloquear a MetaMask
2. Conectar a carteira ao site do MapleStory Universe
3. Coletar o menor preço de cada NFT configurado em `NFT_NAMES`
4. Salvar os dados na planilha Google Sheets

Nas execuções seguintes, se a carteira já estiver conectada, o script pula as etapas de conexão automaticamente.

## Estrutura

```
msu_scraper/
├── main.py            # Ponto de entrada
├── scraper.py         # Lógica principal
├── config.py          # Configurações (não versionado)
├── credentials.json   # Credenciais Google (não versionado)
├── requirements.txt
└── README.md
```