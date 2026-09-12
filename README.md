# Automação Multifoco - Relatório de Vendas e Estoque

Este sistema automatiza todo o ciclo de vida dos dados de Vendas e Estoque da Multifoco. A aplicação realiza a consolidação dos dados de entrada (arquivos CSV), cruza inteligências de estoque por lote e EAN, exporta o panorama consolidado em um arquivo Excel (.xlsx) e o envia a uma API externa. Adicionalmente, o sistema possui capacidade nativa de buscar os arquivos transacionais de forma remota via FTP.

## 1. Funcionalidades Principais
- **Processamento Individualizado:** Lê planilhas brutas sem cabeçalho e aplica regras financeiras e organizacionais de Estoque, Preço de Custo, Validade, Faturamento Atual, entre outras dimensões.
- **Inteligência de Data de Entrada:** O sistema descobre a Data de Entrada analisando os lotes do produto no Estoque (indicadores em colunas fixas).
- **Captura via FTP:** O client FTP automatizado sincroniza planilhas (.csv) hospedadas em servidores parceiros.
- **Comunicação com API:** O relatório final formatado é despachado para a API administrativa.
- **API REST de Imports:** disponibiliza as quatro views atuais em JSON e mantém um download CSV opcional.
- **Agendamento Automático:** O sistema possui um agendador integrado que executa a rotina automaticamente a cada 2 horas.
- **Backup e Retenção:** Arquivos consumidos são arquivados com timestamp, e backups antigos são limpos automaticamente (30-60 dias).

## 2. Como Rodar (Docker - Recomendado)

A aplicação está totalmente "dockerizada", o que elimina a necessidade de instalar dependências localmente.

### Pré-requisitos
- Docker instalado.
- Arquivo `.env` configurado na raiz do projeto.

### Passo 1: Build da Imagem
```bash
docker build -t abs-automation .
```

### Passo 2: Execução do Container
```bash
docker run -d --name abs-app --env-file .env abs-automation
```

### Comandos Úteis
*   **Ver Logs:** `docker logs -f abs-app`
*   **Parar o Container:** `docker stop abs-app`
*   **Iniciar o Container:** `docker start abs-app`

---

## 3. Estrutura do Projeto
- **`main.py`**: Motor primário da automação. Orquestra o FTP, Pandas e API.
- **`core/`**: Módulos de processamento de dados (Pandas):
  - `Col_data_entrada.py`, `Col_estoque.py`, `Col_Custo.py`, etc.
- **`utils/`**: Utilitários de sistema:
  - `api_client.py`: Comunicação com a API.
  - `ftp_client.py`: Sincronização de arquivos via FTP.
  - `Disparo.py`: Gerenciamento do agendamento (scheduler).
  - `exporter_excel.py`: Geração do arquivo XLSX.
- **`imports/`**: Onde os arquivos CSV brutos são processados.
- **`output/`**: Onde os relatórios XLSX finais são gerados.

## 4. Configuração (.env)

Crie um arquivo `.env` na raiz com os seguintes parâmetros:

```env
API_EMAIL="seu_email"
API_PASS="sua_senha"
BASE_URL="http://url_da_api"

FTP_HOST="host_ftp"
FTP_PORT=21
FTP_USER="usuario_ftp"
FTP_PASS="senha_ftp"

VIEW_VENDAS="dbo.VW_MULTFOCO_VENDAS"
VIEW_ESTOQUE="dbo.VW_MULTIFOCO_ESTOQUE"
VIEW_METAS="dbo.VW_MULTIFOCO_METAS"
VIEW_VENDEDORES="dbo.VW_MULTIFOCO_VENDEDORES"

# Token Bearer estático usado para proteger a consulta
IMPORTS_API_TOKEN="cole-aqui-um-token-longo-e-secreto"

# Bind da API desta instância
IMPORTS_API_HOST="0.0.0.0"
IMPORTS_API_PORT=8000
```

## 5. Desenvolvimento Local (Opcional)

Se preferir rodar sem Docker, utilize um ambiente virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

## 6. Consulta das tabelas atuais

Com a aplicação em execução, o sistema consumidor deve enviar o token configurado
em `IMPORTS_API_TOKEN` no cabeçalho `Authorization`:

```bash
curl \
  -H "Authorization: Bearer SEU_TOKEN" \
  http://localhost:8000/imports/atuais
```

A resposta possui quatro propriedades, e cada uma contém uma lista de registros:

```json
{
  "METAS": [{ "nome_da_coluna": "valor" }],
  "VENDAS": [{ "nome_da_coluna": "valor" }],
  "VENDEDORES": [{ "nome_da_coluna": "valor" }],
  "ESTOQUE": [{ "nome_da_coluna": "valor" }]
}
```

Os valores são retornados como texto para preservar códigos, EANs, CNPJs e zeros à
esquerda. Campos vazios são retornados como `null`. O endpoint transmite o JSON em
fluxo, evitando manter toda a tabela de vendas na memória.

Se ainda for necessário baixar os quatro CSVs em um arquivo ZIP:

```bash
curl -OJ \
  -H "Authorization: Bearer SEU_TOKEN" \
  http://localhost:8000/imports/atuais.zip
```

As quatro views são atualizadas a cada execução agendada da automação.
O host e a porta podem ser alterados pelas variáveis `IMPORTS_API_HOST` e `IMPORTS_API_PORT`.
O token é estático e não expira automaticamente; para trocá-lo, atualize o `.env` e reinicie a aplicação.

Em um servidor com múltiplas instâncias usando `network_mode: host`, configure uma porta
diferente manualmente no `.env` de cada instância.
