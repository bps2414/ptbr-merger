from pathlib import Path


STATIC = Path("src/web/static")


def test_hub_navigation_labels_are_present():
    html = (STATIC / "index.html").read_text(encoding="utf-8")

    for label in ("Inicio", "Workflows", "Fila", "Arquivos locais", "Receitas", "Perfis", "Ferramentas", "Configuracoes"):
        assert label in html


def test_ui_does_not_present_future_integrations_as_active_features():
    html = (STATIC / "index.html").read_text(encoding="utf-8")

    assert "Busca automatica, qBittorrent e indexers fazem parte da visao futura" in html
    assert 'data-screen="indexers"' not in html
    assert 'data-screen="trackers"' not in html
