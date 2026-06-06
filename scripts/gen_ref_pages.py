"""Generate one API-reference page per module (+ a nav tree) from the package source.

Run automatically by the mkdocs `gen-files` plugin at build time — it walks src/<package> and emits a
virtual `reference/<module>.md` for each module containing a single mkdocstrings `:::` directive, plus a
`SUMMARY.md` that `literate-nav` turns into the collapsible API-reference nav. Standard mkdocstrings
recipe; no manual per-module stubs to maintain.
"""

from pathlib import Path

import mkdocs_gen_files

PACKAGE = "dbt_column_lineage"

nav = mkdocs_gen_files.Nav()
src = Path(__file__).parent.parent / "src"

for path in sorted((src / PACKAGE).rglob("*.py")):
    module_path = path.relative_to(src).with_suffix("")
    doc_path = path.relative_to(src).with_suffix(".md")
    full_doc_path = Path("reference", doc_path)
    parts = tuple(module_path.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
        doc_path = doc_path.with_name("index.md")
        full_doc_path = full_doc_path.with_name("index.md")
    elif parts[-1] == "__main__":
        continue
    if not parts:
        continue
    nav[parts] = doc_path.as_posix()
    with mkdocs_gen_files.open(full_doc_path, "w") as fd:
        fd.write(f"::: {'.'.join(parts)}")
    mkdocs_gen_files.set_edit_path(full_doc_path, path)

with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as nav_file:
    nav_file.writelines(nav.build_literate_nav())
