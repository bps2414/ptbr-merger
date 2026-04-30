# Roadmap

Este roadmap mantem o escopo atual: ferramenta local para workflows de midia, com foco em seguranca operacional e clareza para quem avalia o repositorio.

## Curto prazo

- Adicionar pipeline CI para `pytest -q` e `python -m compileall src tests`.
- Versionar screenshots reais da interface web local.
- Melhorar mensagens de erro do modo web para usuarios nao tecnicos.
- Reduzir a responsabilidade de `src/trigger.py` sem mudar comportamento.

## Medio prazo

- Separar melhor ranking, fallback e recovery em servicos menores.
- Ampliar perfis de idioma alem do PT-BR.
- Melhorar exportacao de relatorios e receitas.
- Tornar o setup do FFmpeg mais previsivel em diferentes maquinas Windows.

## Fora do escopo atual

- Transformar o projeto em SaaS ou servico multiusuario.
- Baixar conteudo por conta propria sem integracao com as ferramentas locais do usuario.
- Trocar Radarr/qBittorrent/Bazarr por uma arquitetura nova.
- Criar um editor audiovisual completo com waveform e edicao manual detalhada.
