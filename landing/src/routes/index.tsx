import { createFileRoute } from "@tanstack/react-router";
import {
  ArrowDown,
  ArrowRight,
  Ban,
  Check,
  CircleCheck,
  Clock3,
  Copy,
  Eye,
  ExternalLink,
  FolderTree,
  Github,
  Hash,
  Linkedin,
  Menu,
  Network,
  ShieldCheck,
  Sparkles,
  X,
  Zap,
} from "lucide-react";
import { useState } from "react";

import profileAssetUrl from "../assets/anthero-profile.jpg";

const GITHUB = "https://github.com/theroverse/athena";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Athena — a planta baixa do seu projeto para IA" },
      {
        name: "description",
        content:
          "Athena indexa seu repositório de baixo para cima e gera resumos que dão contexto de arquitetura real a qualquer conversa com Claude Code.",
      },
      { property: "og:title", content: "Athena — contexto de arquitetura sem reler o projeto inteiro" },
      {
        property: "og:description",
        content: "Resumos incrementais, bottom-up, com cache por hash — a IA para de esquecer seu projeto a cada conversa.",
      },
      { property: "og:type", content: "website" },
      { property: "og:url", content: "https://theroverse.github.io/athena/" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
    links: [{ rel: "canonical", href: "https://theroverse.github.io/athena/" }],
  }),
  component: Index,
});

const skills = [
  ["Bottom-up de verdade", "Arquivos primeiro, depois pastas — só a partir dos resumos dos filhos"],
  ["Cache incremental por hash", "Reindexar só toca o que mudou de verdade"],
  [".gitignore + .athenaignore", "Respeita as exclusões do projeto, com regras extras opcionais"],
  ["Trava --max-files", "Recusa indexar acima de 300 arquivos sem confirmação explícita"],
  ["--dry-run sem custo", "Veja o que seria processado antes de gastar uma chamada"],
  ["Binários ignorados", "Detecção automática, sem erro, sem configuração"],
  ["Truncamento inteligente", "Arquivos gigantes são cortados antes de chegar ao Claude"],
  ["Limpeza de órfãos", "Resumos de itens deletados somem sozinhos na próxima indexação"],
  ["Zero dependências", "Só Python 3.10+ da biblioteca padrão"],
  ["CI multiplataforma", "Testado em Ubuntu, Windows e macOS, Python 3.10 e 3.12"],
  ["show <caminho>", "Consulte qualquer resumo já indexado sem gastar uma nova chamada"],
  ["Parte da suíte", "Thero roda por você; Zeus consome o índice para planejar"],
];

function CopyCommand({ command, compact = false }: { command: string; compact?: boolean }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(command);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div className={`command ${compact ? "command-compact" : ""}`}>
      <code><span>$</span> {command}</code>
      <button type="button" onClick={copy} aria-label="Copiar comando" title="Copiar comando">
        {copied ? <Check size={17} /> : <Copy size={17} />}
      </button>
    </div>
  );
}

// Glifo real da Athena (mesmo de theroverse/src/components/icons/
// EcosystemIcon.tsx e das cores oficiais em ecosystem.ts: #10B981/#34D399)
// - antes essa marca usava o icone generico Network do lucide.
function AthenaMark({ size = 34 }: { size?: number }) {
  return (
    <span className="brand-mark" style={{ width: size, height: size }} aria-hidden="true">
      <svg viewBox="0 0 64 64" width={Math.round(size * 0.85)} height={Math.round(size * 0.85)}>
        <path d="M20 17 A 19 19 0 0 1 44 17" fill="none" stroke="#34D399" strokeWidth="2" strokeLinecap="round" strokeDasharray="4 3" strokeOpacity="0.8" />
        <path d="M32 9 L52 43 L32 35 L12 43 Z" fill="#10B981" fillOpacity="0.16" stroke="#10B981" strokeWidth="3.25" strokeLinejoin="round" strokeLinecap="round" />
        <path d="M32 16 V35" stroke="#34D399" strokeWidth="2" strokeLinecap="round" />
        <circle cx="20" cy="53" r="2.5" fill="#059669" />
        <circle cx="32" cy="53" r="2.5" fill="#10B981" />
        <circle cx="44" cy="53" r="2.5" fill="#059669" />
        <path d="M20 50 L28 41 M32 50 V41 M44 50 L36 41" stroke="#10B981" strokeWidth="1.75" strokeLinecap="round" strokeOpacity="0.8" />
      </svg>
    </span>
  );
}

function Header() {
  const [open, setOpen] = useState(false);
  return (
    <header className="site-header">
      <a href="#top" className="brand" aria-label="Athena, início">
        <AthenaMark />
        <span>athena</span>
      </a>
      <nav className="desktop-nav" aria-label="Navegação principal">
        <a href="#suite">A suíte</a>
        <a href="#recursos">Recursos</a>
        <a href="#comparativo">Comparativo</a>
        <a href="#autor">Autor</a>
      </nav>
      <a className="header-cta" href={GITHUB} target="_blank" rel="noreferrer">
        <Github size={17} /> GitHub <ExternalLink size={13} />
      </a>
      <button className="menu-button" type="button" onClick={() => setOpen(!open)} aria-label={open ? "Fechar menu" : "Abrir menu"}>
        {open ? <X /> : <Menu />}
      </button>
      {open && (
        <nav className="mobile-nav" aria-label="Navegação móvel">
          <a href="#suite" onClick={() => setOpen(false)}>A suíte</a>
          <a href="#recursos" onClick={() => setOpen(false)}>Recursos</a>
          <a href="#comparativo" onClick={() => setOpen(false)}>Comparativo</a>
          <a href="#autor" onClick={() => setOpen(false)}>Autor</a>
          <a href={GITHUB} target="_blank" rel="noreferrer">Abrir no GitHub</a>
        </nav>
      )}
    </header>
  );
}

function Index() {
  return (
    <main id="top">
      <Header />

      <section className="hero shell">
        <div className="hero-copy">
          <div className="eyebrow"><span /> Open source · Python 3.10+ · Stdlib only</div>
          <h1>Seu projeto tem<br /><em>uma planta baixa agora.</em></h1>
          <p className="hero-lede">
            Athena percorre o repositório e pede ao Claude Code um resumo de cada arquivo — depois de cada pasta, de baixo para cima — até chegar a uma visão completa do projeto. Nenhuma IA precisa reabrir tudo de novo para entender onde está o quê.
          </p>
          <div className="hero-actions">
            <a className="button button-primary" href="#instalar">Instalar a Athena <ArrowDown size={18} /></a>
            <a className="button button-secondary" href={GITHUB} target="_blank" rel="noreferrer"><Github size={18} /> Ver código</a>
          </div>
          <div className="hero-proof">
            <span><CircleCheck size={16} /> Zero dependências Python</span>
            <span><CircleCheck size={16} /> Cache incremental por hash</span>
            <span><CircleCheck size={16} /> Funciona sozinha ou com a suíte</span>
          </div>
        </div>

        <div className="hero-visual" aria-label="Demonstração do comando athena index">
          <div className="terminal-window">
            <div className="terminal-bar"><i /><i /><i /><span>~/seu-projeto — athena</span></div>
            <div className="terminal-body">
              <p><b>$</b> python athena.py index .</p>
              <p className="muted">Escaneando o projeto (.gitignore respeitado)...</p>
              <p><strong>✓</strong> 214 arquivos resumidos, 38 pastas mapeadas</p>
              <p><strong>✓</strong> .athena/ gerado com cache incremental</p>
              <div className="terminal-divider" />
              <p><b>$</b> python athena.py show .</p>
              <p className="muted">[resumo do projeto pronto para qualquer conversa]</p>
              <p><span className="thero-dot">●</span> Thero pode rodar isso por você</p>
              <p><span className="zeus-dot">●</span> Zeus já pode consumir esse índice</p>
              <p className="ready">Pronto. Contexto sem reabrir arquivo por arquivo. <span className="cursor" /></p>
            </div>
          </div>
          <div className="floating-chip chip-one"><Hash size={15} /> cache por hash</div>
          <div className="floating-chip chip-two"><ShieldCheck size={15} /> --max-files protege sua cota</div>
        </div>
      </section>

      <section className="trust-strip" aria-label="Benefícios principais">
        <div className="shell trust-grid">
          <div><strong>1 comando</strong><span>para mapear o repositório inteiro</span></div>
          <div><strong>Bottom-up</strong><span>pastas resumidas a partir dos filhos</span></div>
          <div><strong>Reindexação barata</strong><span>cache incremental por conteúdo</span></div>
          <div><strong>Sem lock-in</strong><span>tudo em Markdown dentro do seu projeto</span></div>
        </div>
      </section>

      <section className="problem-section shell">
        <div className="section-kicker">O problema não é a IA esquecer</div>
        <div className="problem-heading">
          <h2>É você pagar de novo<br />pelo contexto que ela já viu.</h2>
          <p>Sem um mapa do projeto, cada conversa recomeça do zero: reler arquivos, redescobrir a arquitetura, torcer para não esbarrar num pacote que ninguém documentou.</p>
        </div>
        <div className="before-after">
          <article className="pain-column">
            <span className="state-label">Sem Athena</span>
            <ul>
              <li><X size={16} /> Você reabre arquivo por arquivo para lembrar como o projeto funciona</li>
              <li><X size={16} /> Cada conversa com IA começa sem memória de arquitetura</li>
              <li><X size={16} /> Onboarding em projeto grande consome dias só de leitura</li>
              <li><X size={16} /> Código legado ou pacotes privados viram caixa-preta</li>
            </ul>
          </article>
          <div className="transformation-arrow"><ArrowRight /></div>
          <article className="gain-column">
            <span className="state-label">Com Athena</span>
            <ul>
              <li><Check size={16} /> Uma planta baixa gerada uma vez, consultada sempre que precisar</li>
              <li><Check size={16} /> A IA carrega contexto de arquitetura sem reler o repositório</li>
              <li><Check size={16} /> Quem chega agora entende a estrutura em minutos, não dias</li>
              <li><Check size={16} /> Cache incremental mantém o índice barato de atualizar</li>
            </ul>
          </article>
        </div>
      </section>

      <section id="suite" className="suite-section">
        <div className="shell">
          <div className="section-head light">
            <div><span className="section-kicker">Uma suíte. Três responsabilidades.</span><h2>Prepare. Entenda. Planeje.</h2></div>
            <p>Athena é a camada de entendimento: transforma código em contexto que Thero instala e Zeus consome para planejar.</p>
          </div>
          <div className="suite-flow">
            <article className="suite-item thero-item">
              <div className="suite-number">01</div>
              <div className="suite-icon"><ShieldCheck /></div>
              <div className="suite-copy"><span>Prepare</span><h3>Thero</h3><p>Instala skills, consolida regras, preserva configurações existentes e pode rodar a Athena automaticamente por você.</p></div>
              <a href="https://theroverse.github.io/thero/" target="_blank" rel="noreferrer">Conhecer o Thero <ArrowRight size={16} /></a>
            </article>
            <article className="suite-item athena-item self">
              <div className="suite-number">02</div>
              <div className="suite-icon"><Network /></div>
              <div className="suite-copy"><span>Você está aqui</span><h3>Athena</h3><p>Transforma o repositório em uma planta baixa: resumos de arquivos e pastas, de baixo para cima, com cache incremental por hash.</p></div>
              <a href="#top" aria-current="page">Esta página <ArrowRight size={16} /></a>
            </article>
            <article className="suite-item zeus-item">
              <div className="suite-number">03</div>
              <div className="suite-icon"><Zap /></div>
              <div className="suite-copy"><span>Planeje</span><h3>Zeus</h3><p>Cruza sua tarefa com o índice da Athena, identifica arquivos relevantes, riscos e passos antes de pedir a execução.</p></div>
              <a href="https://theroverse.github.io/zeus/" target="_blank" rel="noreferrer">Conhecer o Zeus <ArrowRight size={16} /></a>
            </article>
          </div>
          <div className="tree-diagram-wrap">
            <div className="tree-diagram-bar"><i /><i /><i /><span>.athena/ — saída gerada</span></div>
            <pre className="tree-diagram">{`projeto/
├── src/
│   ├── index.js
│   └── components/
│       └── Button.tsx
└── `}<span className="hl">.athena/</span>{`
    ├── manifest.json      `}<span className="dim">{`// cache incremental por hash`}</span>{`
    ├── summary.md         `}<span className="dim">{`// resumo raiz, cópia de conveniência`}</span>{`
    └── tree/
        ├── src/
        │   ├── index.js.md
        │   └── components/
        │       ├── _dir_summary.md
        │       └── Button.tsx.md
        └── _dir_summary.md`}</pre>
            <div className="system-caption"><Eye size={14} /><span>arquivos primeiro</span><ArrowRight size={12} /><span>pastas a partir dos filhos</span><ArrowRight size={12} /><span>planta baixa do projeto</span></div>
          </div>
        </div>
      </section>

      <section id="comparativo" className="comparison-section shell">
        <div className="section-head">
          <div><span className="section-kicker">Menos releitura por design</span><h2>O ganho vem do mapa pronto,<br />não de uma promessa mágica.</h2></div>
          <p>Cada tarefa que exigiria reabrir vários arquivos para entender o contexto passa a consultar um resumo que já existe.</p>
        </div>
        <div className="scenario-note"><Sparkles size={15} /> Cenário ilustrativo — os números abaixo demonstram o mecanismo, não um benchmark universal.</div>
        <div className="comparison-grid">
          <div className="comparison-card without">
            <div className="comparison-title"><span>Entender um módulo sem Athena</span><small>fluxo reativo</small></div>
            <div className="metric"><div><span>Arquivos reabertos</span><strong>14</strong><small>por tarefa, ilustrativo</small></div><div className="meter"><i style={{ width: "82%" }} /></div></div>
            <div className="metric"><div><span>Tempo até entender</span><strong>~25min</strong><small>estimativa ilustrativa</small></div><div className="meter"><i style={{ width: "76%" }} /></div></div>
            <div className="timeline"><Clock3 /><span>abrir → ler → abrir de novo → ler mais → entender</span></div>
          </div>
          <div className="comparison-card with">
            <div className="comparison-title"><span>A mesma tarefa com Athena</span><small>fluxo orientado</small></div>
            <div className="metric"><div><span>Arquivos reabertos</span><strong>2</strong><small>por tarefa, ilustrativo</small></div><div className="meter"><i style={{ width: "20%" }} /></div></div>
            <div className="metric"><div><span>Tempo até entender</span><strong>~3min</strong><small>estimativa ilustrativa</small></div><div className="meter"><i style={{ width: "15%" }} /></div></div>
            <div className="timeline"><Zap /><span>consultar índice → entender → agir</span></div>
          </div>
        </div>
        <div className="mechanism-row">
          <div><Hash /><strong>Cache incremental</strong><span>reindexa só o que mudou</span></div>
          <div><FolderTree /><strong>Bottom-up</strong><span>pastas resumidas a partir dos filhos</span></div>
          <div><ShieldCheck /><strong>Trava de custo</strong><span>--max-files e --dry-run protegem sua cota</span></div>
        </div>
      </section>

      <section id="recursos" className="skills-section">
        <div className="shell skills-layout">
          <div className="skills-copy">
            <span className="section-kicker">Feita para rodar sem susto</span>
            <h2>Um índice confiável, gerado com cautela.</h2>
            <p>Cada arquivo novo ou alterado custa uma chamada real ao Claude. Athena assume isso como restrição de design, não como detalhe de rodapé.</p>
            <div className="context-rule"><Ban /><div><strong>Nada de surpresa na fatura</strong><span>--max-files trava por padrão em 300 arquivos sem confirmação explícita.</span></div></div>
          </div>
          <div className="skills-list">
            {skills.map(([name, description]) => (
              <div className="skill-row" key={name}><span className="skill-check"><Check size={14} /></span><div><strong>{name}</strong><span>{description}</span></div></div>
            ))}
          </div>
        </div>
      </section>

      <section id="instalar" className="install-section shell">
        <div className="install-grid">
          <div>
            <span className="section-kicker">Comece em minutos</span>
            <h2>Um comando hoje.<br />Contexto pronto amanhã.</h2>
            <p>Clone o projeto e rode a indexação na raiz do seu repositório. A Athena não toca no seu código — só lê e resume.</p>
            <div className="requirements"><span><Check /> Python 3.10+</span><span><Check /> Claude Code autenticado</span><span><Check /> git (opcional, para clonar)</span></div>
          </div>
          <div className="install-terminal">
            <div className="terminal-bar"><i /><i /><i /><span>instalação</span></div>
            <div className="install-commands">
              <CopyCommand command="git clone https://github.com/theroverse/athena.git" compact />
              <CopyCommand command="cd athena" compact />
              <CopyCommand command="python athena.py index ." compact />
            </div>
            <div className="install-result"><CircleCheck /> .athena/ gerado · manifest.json com cache · comando show pronto</div>
          </div>
        </div>
        <div className="mode-grid">
          <div><code>athena index .</code><span>Indexa o projeto usando o cache</span></div>
          <div><code>athena index --dry-run</code><span>Mostra o que seria processado, sem custo</span></div>
          <div><code>athena index --force</code><span>Ignora o cache, reindexa tudo</span></div>
          <div><code>athena show src/</code><span>Consulta um resumo já gerado</span></div>
        </div>
      </section>

      <section id="autor" className="author-section">
        <div className="shell author-grid">
          <div className="author-photo-wrap"><img src={profileAssetUrl} alt="Anthero Vieira Neto" width={200} height={200} loading="lazy" /><span>18 anos<br />construindo<br />software</span></div>
          <div className="author-copy">
            <span className="section-kicker">Nascida de um problema real</span>
            <h2>Reimplementada de uma ferramenta que já salvou um time.</h2>
            <p className="author-lede">Sou <strong>Anthero Vieira Neto</strong>, arquiteto de software sênior e DevOps Engineer. Trabalho com TypeScript, Python, Kubernetes e IA aplicada a produtos reais — do código à cultura de entrega.</p>
            <p>A primeira versão da Athena nasceu anos atrás, numa empresa sem documentação, sem dev sênior disponível e com pacotes privados que ninguém conseguia ler — resultado em retrabalho e bugs em cantos do código que ninguém mapeava. Resumos recursivos resolveram aquilo então; esta é a mesma ideia, reconstruída para rodar no seu terminal.</p>
            <div className="author-links">
              <a href="https://www.linkedin.com/in/anthero-vieira-neto-aa7a6b8a" target="_blank" rel="noreferrer"><Linkedin size={18} /> LinkedIn <ExternalLink size={13} /></a>
              <a href="https://github.com/netovieira" target="_blank" rel="noreferrer"><Github size={18} /> GitHub <ExternalLink size={13} /></a>
            </div>
          </div>
        </div>
      </section>

      <section className="final-cta">
        <div className="shell final-inner">
          <span className="final-mark" aria-hidden="true"><Network size={30} /></span>
          <span className="section-kicker">Seu projeto já tem a história</span>
          <h2>Dê a ele uma planta baixa<br />que a IA consegue ler.</h2>
          <p>Open source, transparente e pronto para o seu próximo repositório.</p>
          <div className="hero-actions">
            <a className="button button-primary" href={GITHUB} target="_blank" rel="noreferrer"><Github size={18} /> Começar no GitHub</a>
            <a className="button button-dark-outline" href="https://github.com/theroverse/athena/blob/main/README.md" target="_blank" rel="noreferrer">Ler documentação <ArrowRight size={17} /></a>
          </div>
        </div>
      </section>

      <section className="final-cta theroverse-cta">
        <div className="shell final-inner">
          <span className="section-kicker">Parte de um ecossistema maior</span>
          <h2>Athena é uma peça do <em>Theroverse</em>.</h2>
          <p>Thero comanda, Athena mapeia o projeto, Zeus planeja antes de qualquer mudança — conheça as outras ferramentas abertas do ecossistema.</p>
          <div className="hero-actions">
            <a className="button button-primary" href="https://theroverse.github.io/" target="_blank" rel="noreferrer">Explorar o Theroverse <ArrowRight size={17} /></a>
          </div>
        </div>
      </section>

      <footer>
        <div className="shell footer-inner">
          <a href="#top" className="brand"><AthenaMark size={28} /><span>athena</span></a>
          <p>A planta baixa do seu projeto, pronta para qualquer conversa com IA.</p>
          <div><a href="https://theroverse.github.io/" target="_blank" rel="noreferrer">Theroverse</a><a href="https://theroverse.github.io/thero/" target="_blank" rel="noreferrer">Thero</a><a href="https://theroverse.github.io/zeus/" target="_blank" rel="noreferrer">Zeus</a><a href="https://github.com/theroverse/athena/blob/main/LICENSE" target="_blank" rel="noreferrer">MIT License</a></div>
          <small>© 2026 Anthero Vieira Neto</small>
        </div>
      </footer>
    </main>
  );
}
