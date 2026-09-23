FILE_SUMMARY_PROMPT = r"""
Você está gerando um resumo técnico compacto de UM arquivo de código,
para ser usado como contexto por uma IA em tarefas futuras nesse
repositório (sem precisar reabrir o arquivo inteiro).

Caminho do arquivo (relativo à raiz do projeto): {relative_path}

Conteúdo do arquivo:

---BEGIN FILE---
{content}
---END FILE---

Produza um resumo em Markdown, direto e denso em informação, contendo:

- **Propósito**: o que este arquivo faz, em 1-3 frases.
- **API pública / exports**: funções, classes, componentes, tipos ou
  rotas exportadas (nome + assinatura resumida), se houver.
- **Dependências relevantes**: principais imports/side-effects que
  quem for mexer aqui precisa saber (ex.: chama uma API externa, lê
  variável de ambiente, depende de outro módulo específico).
- **Pontos de atenção**: comportamento não óbvio, invariantes,
  workarounds, ou riscos ao modificar este arquivo (se houver).

Regras:

- Não inclua o conteúdo do arquivo de volta na resposta.
- Não use markdown fences (```) ao redor da resposta.
- Seja conciso: isto é um resumo, não uma cópia comentada do arquivo.
- Se o arquivo for trivial (ex.: config simples, barrel de exports),
  diga isso em uma linha em vez de forçar as quatro seções.
"""

FOLDER_SUMMARY_PROMPT = r"""
Você está gerando um resumo técnico compacto de UMA PASTA de um
repositório de código, a partir dos resumos já gerados dos arquivos e
subpastas diretamente dentro dela. O objetivo é dar a uma IA uma visão
do que essa pasta faz sem precisar ler cada arquivo individualmente.

Caminho da pasta (relativo à raiz do projeto): {relative_path}

Itens diretamente dentro desta pasta (arquivos e subpastas, já
resumidos):

---BEGIN CHILDREN---
{children}
---END CHILDREN---

Produza um resumo em Markdown, direto e denso em informação, contendo:

- **Responsabilidade da pasta**: o que este módulo/área do projeto
  representa, em 1-3 frases.
- **Principais peças**: os arquivos/subpastas mais importantes e como
  se relacionam (não repita a lista inteira, destaque o que importa).
- **Pontos de entrada**: se houver um arquivo "principal" (index,
  main, route handler, etc.), mencione qual é.

Regras:

- Não use markdown fences (```) ao redor da resposta.
- Seja conciso: isto é um resumo de resumos, não uma lista exaustiva.
- Se a pasta for simples (poucos arquivos, propósito óbvio), diga isso
  em poucas linhas em vez de forçar as três seções.
"""

LOG_SUMMARY_PROMPT = r"""
Você está condensando um trecho de LOGS/SAÍDA de execução para servir
como contexto limpo a outra IA. Não é uma conversa: entregue só fatos
técnicos, sem saudação, preâmbulo ou fecho.

Fonte (opcional): {source}

Conteúdo dos logs:

---BEGIN LOGS---
{content}
---END LOGS---

Produza um resumo direto contendo, quando houver evidência:

- **O que aconteceu**: resultado geral (sucesso/falha/parcial) em 1-2
  frases.
- **Erros relevantes**: mensagens de erro/tracebacks importantes,
  deduplicados e resumidos (não copie centenas de linhas repetidas).
- **Suspeita de causa**: o que provavelmente provocou, se inferível.
- **Próximos passos**: ações que os logs indicam, se houver.

Regras:

- Comece já pelo conteúdo técnico, sem "Claro", "Aqui está", "Sure" ou
  qualquer frase de cortesia.
- Não use markdown fences (```) ao redor da resposta.
- Se não houver nada tecnicamente relevante, responda apenas uma linha
  dizendo isso.
"""
