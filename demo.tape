# Demo recording script for the README GIF.
# Render with VHS (https://github.com/charmbracelet/vhs):  vhs demo.tape
# Runs against the committed tests/fixtures/jaffle example — no warehouse needed.
# Requires: jq, and `uv sync` to have created .venv.

Output docs/demo.gif

Set Shell bash
Set FontSize 18
Set Width 1320
Set Height 760
Set Theme "Catppuccin Mocha"
Set Padding 24
Set TypingSpeed 45ms

# --- setup (hidden) ---
Hide
Type "uv sync >/dev/null 2>&1 && source .venv/bin/activate" Enter
Type "M=tests/fixtures/jaffle/manifest.json; C=tests/fixtures/jaffle/catalog.json" Enter
Type "clear" Enter
Show

# --- beat 1: lineage that keeps the transformation chain ---
Type "# Column lineage that keeps the TRANSFORMATIONS, not just A -> B:" Enter
Sleep 800ms
Type "dbt-column-lineage extract --manifest $M --catalog $C | jq -c '.edges[] | {to: .downstream.column, from: .upstream.column, via: [.transforms[].kind]}'" Enter
Sleep 4500ms

# --- beat 2: trace a column to its sources ---
Type "# Trace a column back to its sources, transitively:" Enter
Sleep 800ms
Type "dbt-column-lineage upstream model.jaffle.customers.lifetime_value --manifest $M --catalog $C" Enter
Sleep 3500ms

# --- beat 3: no warehouse catalog needed — schemas inferred from the SQL ---
Type "# ...and it works with NO warehouse catalog (schemas inferred from compiled SQL):" Enter
Sleep 800ms
Type "dbt-column-lineage extract --manifest $M --schema-mode inferred | jq '.edges | length'" Enter
Sleep 3500ms
