# Athena

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Stdlib only](https://img.shields.io/badge/dependencies-stdlib--only-brightgreen.svg)

**Dá a uma IA (ou a você) uma visão de todo o projeto sem precisar
reabrir arquivo por arquivo toda vez.**

Você já entrou num projeto sem documentação, sem arquitetura mapeada,
onde ninguém sabe mais o que cada pasta faz? A Athena resolve
exatamente isso: percorre o repositório recursivamente e pede ao
[Claude Code](https://claude.com/claude-code) um resumo de cada
arquivo — de baixo para cima, primeiro cada arquivo, depois cada
pasta a partir dos resumos dos seus filhos — até chegar num resumo da
raiz do projeto. O resultado é uma "planta baixa" do código, gerada
automaticamente, que tanto você quanto uma IA podem consultar em vez
de reler tudo do zero a cada pergunta.

Reimplementação de uma ferramenta que já usei profissionalmente (mesmo
nome, mesma ideia): num projeto sem documentação, sem arquitetura
mapeada e com pacotes privados que ninguém conseguia ler, gerar esses
resumos recursivos foi o que resolveu o retrabalho e os bugs em lugares
não mapeados.

## Por que usar

- **Você entende um projeto grande sem ler tudo.** Útil pra quem está
  começando e caiu de paraquedas num codebase de anos — e útil pra
  quem já é sênior e só quer relembrar rápido "o que faz essa pasta".
- **A IA para de "esquecer" o projeto a cada pergunta.** Sem um
  índice, toda conversa com o Claude começa do zero, reabrindo
  arquivos. Com a Athena, o contexto de arquitetura já existe em
  disco.
- **Cache incremental de verdade.** Rodar de novo só re-resume o que
  mudou — não reprocessa o projeto inteiro a cada execução.
- **Parte de uma suíte**: o [thero](https://github.com/theroverse/thero)
  configura o Claude Code pra já consultar os resumos da Athena
  automaticamente, e o [Zeus](https://github.com/theroverse/zeus) usa
  esses resumos pra planejar uma tarefa antes de você pedir pro Claude
  executar. Cada um funciona sozinho também.

## Descrição

- Percorre o projeto recursivamente, respeitando o `.gitignore` da
  raiz (e um `.athenaignore` opcional, mesma sintaxe, para exclusões
  extras).
- Para cada arquivo, pede ao Claude um resumo compacto (propósito, API
  pública, dependências relevantes, pontos de atenção).
- Para cada pasta, pede ao Claude um resumo a partir dos resumos dos
  arquivos/subpastas diretamente dentro dela — não relê os arquivos.
- Guarda tudo em `.athena/` na raiz do projeto indexado, espelhando a
  estrutura de pastas.
- Cache incremental por hash (`.athena/manifest.json`): rodar de novo
  só re-resume o que mudou; itens deletados do projeto têm seus
  resumos removidos automaticamente.
- Trava de segurança (`--max-files`): recusa indexar um projeto grande
  demais sem confirmação explícita, já que cada arquivo novo/alterado
  custa uma chamada real ao Claude.
- `--dry-run`: mostra o que seria processado (e o que seria
  reaproveitado do cache) sem gastar nenhuma chamada.

## Requisitos

- Python 3.10+ (só biblioteca padrão, sem dependências externas)
- Claude Code instalado e autenticado (`claude -p`)

## Instalação

```
git clone https://github.com/theroverse/athena.git
cd athena
python athena.py --help
```

## Uso

```
python athena.py index [PASTA]     # gera/atualiza o índice
python athena.py show <caminho>    # mostra um resumo já indexado
python athena.py --help
```

### `index`

```
python athena.py index                    # indexa a pasta atual
python athena.py index /caminho/projeto    # indexa outra pasta
python athena.py index --dry-run           # simula, sem chamar o Claude
python athena.py index --force             # ignora o cache, re-resume tudo
python athena.py index --max-files 1000    # eleva a trava de segurança
```

### `show`

```
python athena.py show src/components/Button.tsx   # resumo de um arquivo
python athena.py show src/components               # resumo de uma pasta
python athena.py show .                             # resumo raiz do projeto
```

## Como funciona

```
projeto/
├── .gitignore              ─┐
├── src/                     │  Athena percorre respeitando
│   ├── index.js             │  .gitignore + .athenaignore
│   └── components/          │  (.git/ e .athena/ sempre ignorados)
│       └── Button.tsx      ─┘
│
└── .athena/                          <- gerado pela Athena
    ├── manifest.json                 <- cache (hash por item)
    ├── summary.md                    <- resumo raiz (cópia de conveniência)
    └── tree/
        ├── _dir_summary.md           <- resumo da raiz
        ├── src/
        │   ├── index.js.md           <- resumo do arquivo
        │   ├── _dir_summary.md       <- resumo da pasta src/
        │   └── components/
        │       ├── Button.tsx.md
        │       └── _dir_summary.md
```

Ordem de execução: arquivos antes das pastas que os contêm (bottom-up),
recursivamente, até a raiz. O resumo de uma pasta é gerado a partir dos
resumos dos seus filhos diretos (arquivos e subpastas) — nunca relendo
o conteúdo bruto dos arquivos de novo.

## Custo e segurança

Cada arquivo ou pasta novo/alterado gera uma chamada real ao
`claude -p`. Por isso:

- `index` recusa rodar contra mais de 300 arquivos de uma vez (padrão),
  a menos que você passe `--max-files` explicitamente maior.
- Use `--dry-run` primeiro em um projeto que você nunca indexou, para
  conferir que o `.gitignore`/`.athenaignore` está excluindo o que
  deveria (ex.: `node_modules/`, `dist/`, `vendor/`) antes de gastar
  chamadas de verdade.
- Arquivos maiores que ~40.000 caracteres são truncados antes de
  enviar ao Claude, para não gerar um prompt gigante em um único
  arquivo.
- Arquivos binários (que não decodificam como UTF-8) são pulados
  automaticamente, sem erro.

## Integração com o Thero

O [`thero`](https://github.com/theroverse/thero) (setup do Claude
Code) pode rodar `athena index .` automaticamente como um passo
opcional (`thero --index`), se a Athena estiver instalada. Veja o
README do `thero` para detalhes.

Existe um segundo par desta ferramenta, o [`zeus`](https://github.com/theroverse/zeus):
um planejador que cruza o pedido do usuário com o índice gerado pela
Athena (via `claude -p`) para decidir quais arquivos reais precisam
ser lidos/editados antes de uma tarefa, escrevendo o resultado em
`.claude/zeus-plan.md`.

## Limitações conhecidas

- Só lê o `.gitignore` da raiz do projeto — não considera `.gitignore`
  aninhados em subpastas.
- Processamento é sequencial (um resumo por vez), não paralelo.
- Não tenta detectar se o `claude` autenticado tem cota/rate limit
  suficiente para o volume de arquivos — use `--dry-run` e
  `--max-files` para se proteger de rodadas grandes demais.

## Projeto

```
athena/
├── athena.py                 # ponto de entrada (python athena.py ...)
├── src/athena/
│   ├── cli.py                  # argparse + orquestração (index/show)
│   ├── settings.py             # nomes de arquivo/pasta, limites
│   ├── ignore.py                # matcher estilo .gitignore
│   ├── hashing.py                 # hash de conteúdo (cache)
│   ├── manifest.py                 # cache incremental (.athena/manifest.json)
│   ├── summarizer/
│   │   ├── prompts.py                # prompts de resumo (arquivo/pasta)
│   │   ├── claude_client.py           # chamada ao "claude -p" (via stdin)
│   │   └── indexer.py                  # varredura + orquestração bottom-up
│   └── system/
│       └── process.py                   # execução de comandos (Windows/POSIX)
├── README.md
└── .gitignore
```

## Autor

**Anthero Vieira Neto**

- E-mail: antherovn@gmail.com
- LinkedIn: https://www.linkedin.com/in/anthero-vieira-neto-aa7a6b8a
- GitHub: http://github.com/netovieira

## Licença

[MIT](./LICENSE)
