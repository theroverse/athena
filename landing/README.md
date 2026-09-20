# Athena — landing page

Site estático (TanStack Start SSG) publicado em https://theroverse.github.io/athena/.

## Desenvolvimento

```
npm install
npm run dev
```

## Build

```
npm run build
```

Gera `dist/client`, pronto para publicação estática (GitHub Pages). O workflow
`.github/workflows/deploy-pages.yml` do repositório builda e publica automaticamente
a cada push em `landing/**` na branch `main`.

Construído com TanStack Start, React 19 e Tailwind CSS v4 — mesma base do
[thero/landing](https://github.com/theroverse/thero/tree/master/landing).
