#!/usr/bin/env python3
"""
skill_search.py — Find skills by keyword from installed skills
Usage: python3 skill_search.py "your search here"
       python3 skill_search.py "authentication"
       python3 skill_search.py "react component animation"
       python3 skill_search.py --list          (list all skill names)

Scans SKILL.md files in each skill directory for name/description.
Works without skills_index.json by reading SKILL.md frontmatter directly.
"""
import json
import sys
import os
import re
from pathlib import Path

# Resolve paths relative to this script's location
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
SKILLS_DIR = REPO_ROOT  # skills are direct children
INDEX_FILE = REPO_ROOT / "skills_index.json"
BUNDLES_FILE = REPO_ROOT / "data" / "bundles.json"
CACHE_FILE = SCRIPT_DIR / ".skill_cache.json"


def parse_skill_md(skill_dir: Path) -> dict:
    """Extract name and description from SKILL.md frontmatter."""
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return None

    try:
        content = skill_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    name = skill_dir.name
    description = ""

    # Try YAML frontmatter: ---\nkey: value\n---
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        frontmatter = fm_match.group(1)
        # Extract name
        name_match = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
        if name_match:
            name = name_match.group(1).strip().strip("'\"")
        # Extract description
        desc_match = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
        if desc_match:
            description = desc_match.group(1).strip().strip("'\"")

    # If no description from frontmatter, grab first meaningful paragraph
    if not description:
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("---") and len(line) > 20:
                description = line[:200]
                break

    return {
        "name": name,
        "description": description,
        "path": skill_dir.name,
        "dir": str(skill_dir),
    }


def load_skills():
    """Load skills from index file or scan directories."""
    # Try skills_index.json first
    if INDEX_FILE.exists():
        try:
            with open(INDEX_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "skills" in data:
                return data["skills"]
            return list(data.values())
        except Exception:
            pass

    # Try cache (rebuilt periodically)
    if CACHE_FILE.exists():
        try:
            cache_stat = CACHE_FILE.stat()
            import time
            # Use cache if less than 1 hour old
            if (time.time() - cache_stat.st_mtime) < 3600:
                with open(CACHE_FILE, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass

    # Scan directories
    print("🔄 Building skill index (first run may take a moment)...")
    skills = []
    if not SKILLS_DIR.exists():
        print(f"❌ Skills directory not found: {SKILLS_DIR}")
        sys.exit(1)

    for item in sorted(SKILLS_DIR.iterdir()):
        if item.is_dir() and not item.name.startswith(".") and item.name not in ("scripts", "data", "node_modules"):
            skill = parse_skill_md(item)
            if skill:
                skills.append(skill)

    # Cache for faster subsequent runs
    try:
        SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(skills, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return skills


def search(query: str, top_n: int = 10):
    skills = load_skills()
    terms = query.lower().split()

    results = []
    for skill in skills:
        name = str(skill.get("name", "")).lower()
        desc = str(skill.get("description", "")).lower()
        path = str(skill.get("path", "")).lower()
        full_text = f"{name} {desc} {path}"

        # Score: name matches count double
        score = sum(full_text.count(t) for t in terms)
        score += sum(name.count(t) * 2 for t in terms)

        # Bonus for exact name match
        if query.lower() in name:
            score += 10

        if score > 0:
            results.append((score, skill))

    results.sort(key=lambda x: -x[0])

    if not results:
        print(f"\n🔍 Nenhuma skill encontrada para: '{query}'")
        print("   Tente termos mais amplos, ex: 'auth', 'deploy', 'test', 'api'\n")
        return

    print(f"\n🎯 Top skills para '{query}':\n")
    for score, skill in results[:top_n]:
        path_val = skill.get("path", "")
        name_val = skill.get("name", path_val)
        desc_val = skill.get("description", "")
        if len(desc_val) > 100:
            desc_val = desc_val[:97] + "..."
        print(f"  📌 {name_val}")
        print(f"     Invocar: \"Use the {path_val} skill to [sua tarefa]\"")
        if desc_val:
            print(f"     Sobre: {desc_val}")
        print()


def list_all():
    skills = load_skills()
    print(f"\n📋 Total de skills instaladas: {len(skills)}\n")
    for skill in skills:
        name = skill.get("name", skill.get("path", "?"))
        desc = skill.get("description", "")
        if len(desc) > 80:
            desc = desc[:77] + "..."
        print(f"  • {name}")
        if desc:
            print(f"    {desc}")
    print()


def list_bundles():
    if not BUNDLES_FILE.exists():
        print("❌ bundles.json não encontrado.")
        print(f"   Caminho esperado: {BUNDLES_FILE}")
        return
    with open(BUNDLES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    bundles = data if isinstance(data, list) else data.get("bundles", [])
    print("\n📦 Bundles Disponíveis:\n")
    for b in bundles:
        name = b.get("name", "?")
        desc = b.get("description", "")
        skills_list = b.get("skills", [])
        print(f"  {name}")
        if desc:
            print(f"    {desc}")
        if skills_list:
            skills_preview = ", ".join(skills_list[:5])
            if len(skills_list) > 5:
                skills_preview += f" (+{len(skills_list)-5} mais)"
            print(f"    Skills: {skills_preview}")
        print()


def rebuild_cache():
    """Force cache rebuild."""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
    skills = load_skills()
    print(f"✅ Cache reconstruído com {len(skills)} skills.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 skill_search.py \"termos de busca\"")
        print("     python3 skill_search.py --bundles")
        print("     python3 skill_search.py --list")
        print("     python3 skill_search.py --rebuild")
        sys.exit(0)

    arg = sys.argv[1]
    if arg in ("--bundles", "-b", "bundles"):
        list_bundles()
    elif arg in ("--list", "-l", "list"):
        list_all()
    elif arg in ("--rebuild", "-r", "rebuild"):
        rebuild_cache()
    else:
        query = " ".join(sys.argv[1:])
        search(query)
