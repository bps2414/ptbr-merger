# Visao geral

PTBRMerger e uma aplicacao local para fluxos de midia com foco inicial em audio PT-BR em arquivos MKV.

O projeto tem duas camadas principais:

- modo web local, voltado para uso manual com arquivos em `input/`;
- automacao legada, integrada a Radarr e qBittorrent para buscar candidatos e continuar o fluxo quando downloads terminam.

## Fluxo manual

```text
MKV alvo + MKV fonte -> inspecao -> plano seguro -> mux -> validacao -> output + relatorio + receita
```

Esse fluxo nao substitui o arquivo original. O resultado final e salvo em `output/` e os detalhes tecnicos ficam em `reports/` e `recipes/`.

## Fluxo automatizado

```text
Radarr -> trigger.py -> analise -> busca/ranking -> qBittorrent -> trigger.py -> mux -> validacao -> feedback no Radarr
```

Esse caminho depende de configuracao externa e deve ser usado com `config.yml` local, nunca versionado.

## Areas importantes

- `src/web/`: servidor local, rotas HTTP e interface.
- `src/workflows/`: workflow manual de audio preferido.
- `src/analyzer.py`: leitura de streams e diagnostico de sincronismo.
- `src/merger.py`: comandos FFmpeg e validacao final.
- `src/trigger.py`: orquestracao do fluxo automatizado.
- `src/tools/`: preflight, status, refresh de webhook e higiene de runtime.
- `tests/`: suite de seguranca comportamental para evoluir sem quebrar o fluxo.
