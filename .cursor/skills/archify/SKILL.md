---
name: archify
description: >-
  Gera diagramas HTML interativos com o Archify local (arquitetura, fluxo,
  sequência, dados). Use quando o usuário pedir diagrama HTML, Archify,
  signal-flow, visual moderno, ou /archify.
disable-model-invocation: true
---

# Archify

Gera um HTML independente com o pacote em `/home/rafael/www/archify/archify`. O contrato completo está em `/home/rafael/www/archify/archify/SKILL.md`. Siga esse arquivo. O que está abaixo só fixa o caminho local e os padrões deste uso.

## Comando

Diretório de trabalho: a raiz do repositório que está sendo desenhado.

```bash
node /home/rafael/www/archify/archify/bin/archify.mjs finalize <type> <candidate.json> <output.html> --quality showcase --json
```

Pasta de cada pedido: `.archify/<type>-<slug>-<YYYYMMDD-HHMMSS>/`, com `candidate.json` e o HTML dentro. `meta.output` é esse HTML, relativo à raiz. Se o browser-check falhar por sandbox (`kill EACCES`), rode de novo fora do sandbox com `--out-dir <pasta>/review-<n>`.

## Padrões

- Texto do diagrama no idioma do usuário. Português não tem catálogo embutido: não defina `meta.locale`. Avise que a interface do visualizador continua em inglês.
- "Moderno", "HTML" ou visual novo: `meta.visual_preset` = `signal-flow`. Sem esse pedido, omita o preset.
- `meta.quality_profile`: `showcase`. Omita `meta.animation` e `meta.viewBox`.
- Sem `git rev-parse HEAD` válido, omita `meta.repository` e não passe `--repo-root`.
- Não descreva revisão visual se ninguém olhou a tela. Um cruzamento que o receipt ainda apontar entra na resposta, numa frase.

## Antes de escrever o JSON

Leia `/home/rafael/www/archify/archify/references/authoring-defaults.md` e o exemplo do tipo em `/home/rafael/www/archify/archify/examples/`. Para arquitetura de sistema, use `web-app.architecture.json` só como forma. Os fatos saem do código e da documentação do repositório alvo, não do exemplo.
