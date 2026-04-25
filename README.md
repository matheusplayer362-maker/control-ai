# Control AI - Sistema de IA Autonoma Local

Aplicativo desktop com inicializacao em 1 clique, interface de chat moderna, backend local FastAPI, memoria persistente, scraping resiliente multi-fonte, validacao de consistencia e modulo de skills dinamico.

## O que este projeto entrega

- Executavel desktop via Electron (`.exe` com `electron-builder`)
- Inicializacao automatica do backend junto com a interface
- Chat contextual com historico persistente em SQLite
- Indicadores de status, modo da IA e nivel de confianca
- Coleta de dados web em tempo real com fallback de parsing
- Validacao entre fontes + score de confianca
- Auto-recuperacao com retries e log de incidentes
- Sistema de skills dinamicas (`backend/skills`)
- Modo offline parcial com LLM local (`llama.cpp`) ou fallback heuristico

## Arquitetura

- Front-end: Electron + HTML/CSS/JS (`desktop/`)
- Back-end: FastAPI (`backend/app/`)
- Nucleo IA local: `llm_router.py`
- Coleta de dados: `scraper.py`
- Validacao e confianca: `validator.py`
- Acoes locais: `actions.py`
- Expansao por skills: `skills.py` + `backend/skills/*.py`
- Persistencia: SQLite em `backend/data/control_ai.db`

## Instalacao automatica (recomendado)

1. Clique duplo em `Install-ControlAI-Automatico.bat`
2. O script faz tudo sozinho:
   - prepara ambiente Python e Node
   - limpa build antigo
   - gera o instalador
   - abre o instalador automaticamente
3. Ao concluir a instalacao, o app abre automaticamente.

## Primeiro inicio apos instalar

1. No primeiro boot, o aplicativo pode levar mais tempo.
2. O backend cria um runtime local em `%LOCALAPPDATA%\Control AI\runtime`.
3. Se o Python do sistema nao estiver configurado, o app usa `py -3`, `python` ou `python3` e instala as dependencias automaticamente nesse runtime.
4. Depois disso, o app abre normalmente nas proximas execucoes.

## Abrir rapido depois da primeira instalacao

1. Clique duplo em `ControlAI-OneClick.bat`
2. Se ja existir instalador em `dist/`, ele abre direto.
3. Se nao existir, o script executa a instalacao automatica completa.

## Gerar instalador manualmente (avancado)

1. `npm run build:installer`
2. O instalador sera gerado em `dist/ControlAI-Setup-<versao>.exe`

## Modelo local (opcional, recomendado)

Para respostas mais avancadas offline:

1. Baixe um modelo GGUF open-source (ex: Mistral, Llama, Qwen quantizado)
2. Salve em `models/llm.gguf`
3. Reinicie o app

Sem modelo, o sistema usa modo heuristico local (continua funcional).

## Endpoints backend

- `GET /health`
- `GET /history/{session_id}`
- `DELETE /history/{session_id}`
- `POST /chat`
- `GET /skills`
- `POST /skills`

## Observacoes importantes

- Coleta web depende da conectividade da rede e da disponibilidade dos sites.
- O sistema evita API paga e usa apenas ferramentas open-source e dados publicos.
- Execucao automatica de comandos locais e intencionalmente restrita por seguranca.

## Proximos upgrades sugeridos

- Motor RAG local com embeddings + vetor DB
- Sandbox real para execucao segura de scripts
- Multi-model router com benchmark automatico por tarefa
- Plugin marketplace local para skills
- Pacote Android com React Native + backend embarcado
